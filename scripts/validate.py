"""Check scholarship records against the schema and the extraction rules.

Usage:
    python scripts/validate.py                 # checks data/records and data/inbox
    python scripts/validate.py data/inbox      # checks one folder
    python scripts/validate.py path/to/file.json

Exit code is 1 if any error is found, so agents (and CI later) can rely on it.
Warnings are printed but do not fail the run.
"""

import json
import sys
from datetime import date
from pathlib import Path

from jsonschema import Draft202012Validator

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = REPO_ROOT / "schema" / "scholarship.schema.json"
DEFAULT_FOLDERS = [REPO_ROOT / "data" / "records", REPO_ROOT / "data" / "inbox"]

# Sites that list scholarships but are not the provider. They may appear in
# source_urls as "secondary", but never as the official apply link.
AGGREGATOR_DOMAINS = [
    "opportunitiesforafricans", "o4af.com", "opportunitiescorners", "opportunitiesinfo",
    "scholarshipsfuture", "brightscholarship", "afterschoolafrica", "scholarsworld",
    "wemakescholars", "globalscholarships", "mastersportal", "scholarshiptab",
    "careershelpdesk", "opportunitiescircle", "european-funding-guide", "blogspot.com",
]


def collect_files(args: list[str]) -> list[Path]:
    """Turn command-line arguments (or the default folders) into a list of JSON files."""
    targets = [Path(a) for a in args] if args else DEFAULT_FOLDERS
    files: list[Path] = []
    for target in targets:
        if target.is_dir():
            for path in sorted(target.glob("*.json")):
                files.append(path)
        elif target.suffix == ".json" and target.exists():
            files.append(target)
        else:
            print(f"Skipping {target}: not a folder or .json file")
    return files


def expected_status(record: dict) -> str | None:
    """Work out what status the dates imply, or None if the dates can't tell us."""
    timeline = record["application_timeline"]
    checked_on = date.fromisoformat(record["last_verified"])
    opening = timeline["opening_date"]
    deadline = timeline["deadline_date"]

    if deadline is not None and date.fromisoformat(deadline) < checked_on:
        return "closed"
    if opening is not None and deadline is not None:
        if date.fromisoformat(opening) <= checked_on:
            return "open"
        return "upcoming"
    return None


def check_rules(record: dict) -> tuple[list[str], list[str]]:
    """Checks the schema cannot express. Returns (errors, warnings)."""
    errors: list[str] = []
    warnings: list[str] = []
    timeline = record["application_timeline"]
    checked_on = date.fromisoformat(record["last_verified"])

    # 1. Status must agree with the dates.
    implied = expected_status(record)
    if implied is not None and record["status"] != implied:
        errors.append(f"status is '{record['status']}' but the dates imply '{implied}'")

    # 2. Urgent flag: open and deadline within 30 days of last_verified.
    should_be_urgent = False
    if record["status"] == "open" and timeline["deadline_date"] is not None:
        days_left = (date.fromisoformat(timeline["deadline_date"]) - checked_on).days
        if 0 <= days_left <= 30:
            should_be_urgent = True
    if timeline["urgent_deadline"] != should_be_urgent:
        errors.append(f"urgent_deadline should be {should_be_urgent}")

    # 3. Opening date must not be after the deadline.
    if timeline["opening_date"] and timeline["deadline_date"]:
        if timeline["opening_date"] > timeline["deadline_date"]:
            errors.append("opening_date is after deadline_date")

    # 4. last_verified cannot be in the future.
    if checked_on > date.today():
        errors.append("last_verified is in the future")

    # 5. Stipend: min <= max, and a currency when an amount is given.
    stipend = record["financial_coverage"]["stipend"]
    low, high = stipend["amount_min"], stipend["amount_max"]
    if low is not None and high is not None and low > high:
        errors.append("stipend amount_min is greater than amount_max")
    if (low is not None or high is not None) and stipend["currency"] is None:
        errors.append("stipend has an amount but no currency")

    # 6. Fee consistency.
    fee = record["application_fee"]
    if fee["required"] is True and fee["paid_to"] in (None, "none"):
        errors.append("application_fee is required but paid_to is not set")
    if fee["amount"] is not None and fee["currency"] is None:
        errors.append("application_fee has an amount but no currency")

    # 7. High confidence needs an official source.
    sources = record["source_urls"]
    has_official = False
    for source in sources:
        if source["type"] == "official":
            has_official = True
    confidence = record["verification_status"]["confidence_score"]
    if confidence >= 0.8 and not has_official:
        errors.append("confidence_score >= 0.8 but no official source is listed")

    # 8. Apply link must not be an aggregator site.
    apply_url = record["official_apply_url"] or ""
    for domain in AGGREGATOR_DOMAINS:
        if domain in apply_url:
            errors.append(f"official_apply_url points to an aggregator ({domain})")

    # Warnings: things a human should look at, but not hard failures.
    if not has_official:
        warnings.append("no official source yet")
    if record["status"] == "unknown":
        warnings.append("status is unknown")
    if confidence < 0.7:
        warnings.append(f"low confidence ({confidence})")

    return errors, warnings


def main() -> int:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    files = collect_files(sys.argv[1:])

    if not files:
        print("No JSON files found.")
        return 0

    error_count = 0
    seen_titles: dict[str, Path] = {}

    for path in files:
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            print(f"ERROR {path}: not valid JSON ({exc})")
            error_count += 1
            continue

        if isinstance(record, list):
            print(f"ERROR {path}: file holds a list; write one object per file")
            error_count += 1
            continue

        schema_errors = []
        for err in validator.iter_errors(record):
            location = "/".join(str(part) for part in err.absolute_path) or "(top level)"
            schema_errors.append(f"{location}: {err.message}")

        if schema_errors:
            # Rule checks assume a schema-valid record, so stop here for this file.
            for message in schema_errors:
                print(f"ERROR {path.name}: {message}")
            error_count += len(schema_errors)
            continue

        rule_errors, warnings = check_rules(record)
        for message in rule_errors:
            print(f"ERROR {path.name}: {message}")
        for message in warnings:
            print(f"warn  {path.name}: {message}")
        error_count += len(rule_errors)

        # The same scholarship in inbox and records is expected (an update).
        # The same title twice in one folder is a duplicate.
        key = path.parent.name + "|" + record["scholarship_title"].strip().lower()
        if key in seen_titles:
            print(f"ERROR {path.name}: same title as {seen_titles[key].name}")
            error_count += 1
        else:
            seen_titles[key] = path

    print()
    if error_count == 0:
        print(f"All checks passed ({len(files)} files).")
        return 0
    print(f"{error_count} error(s) in {len(files)} files.")
    return 1


if __name__ == "__main__":
    sys.exit(main())

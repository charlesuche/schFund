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
LOGOS_DIR = REPO_ROOT / "app" / "static" / "logos"
# Pages must stay small on mobile data; a logo bigger than this should be optimised.
LOGO_MAX_BYTES = 30_000

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

    # 9. We can only be confident about a next cycle that has an expected date.
    if timeline["next_cycle_expected"] is None and timeline["next_cycle_confidence"] != "unknown":
        errors.append("next_cycle_confidence must be 'unknown' when next_cycle_expected is null")

    # 10. The allowed graduation window must not be backwards.
    eligibility = record["eligibility_criteria"]
    earliest = eligibility["degree_completed_earliest"]
    latest = eligibility["degree_completed_latest"]
    if earliest is not None and latest is not None and earliest > latest:
        errors.append("degree_completed_earliest is after degree_completed_latest")

    # 11. A percent must be a percent. The schema checks this too; repeated here
    # so check_rules() is safe to call on its own (e.g. from the loader or tests).
    grade_percent = eligibility["min_grade_percent"]
    if grade_percent is not None and not 0 <= grade_percent <= 100:
        errors.append("min_grade_percent must be between 0 and 100")

    # 12. A logo named in the record must really be in app/static/logos/,
    # otherwise the page would show a broken image.
    logo = record.get("provider_logo")
    if logo is not None:
        logo_path = LOGOS_DIR / logo["file"]
        if not logo_path.is_file():
            errors.append(f"provider_logo file app/static/logos/{logo['file']} does not exist")
        elif logo_path.stat().st_size > LOGO_MAX_BYTES:
            warnings.append(f"provider_logo {logo['file']} is {logo_path.stat().st_size // 1000} KB; optimise it below {LOGO_MAX_BYTES // 1000} KB")

    # Warnings: things a human should look at, but not hard failures.
    if not has_official:
        warnings.append("no official source yet")
    if record["status"] == "unknown":
        warnings.append("status is unknown")
    if confidence < 0.7:
        warnings.append(f"low confidence ({confidence})")

    return errors, warnings


def load_validator() -> Draft202012Validator:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


def check_file(path: Path, validator: Draft202012Validator) -> tuple[dict | None, list[str], list[str]]:
    """Read one record file and run every check on it.

    Returns (record, errors, warnings). record is None when the file could not
    be read as a single JSON object. The loader uses this too, so a record that
    fails here can never reach the database.
    """
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return None, [f"not valid JSON ({exc})"], []

    if not isinstance(record, dict):
        return None, ["file must hold one JSON object; write one record per file"], []

    schema_errors = []
    for err in validator.iter_errors(record):
        location = "/".join(str(part) for part in err.absolute_path) or "(top level)"
        schema_errors.append(f"{location}: {err.message}")
    if schema_errors:
        # Rule checks assume a schema-valid record, so stop here for this file.
        return record, schema_errors, []

    rule_errors, warnings = check_rules(record)
    return record, rule_errors, warnings


def main() -> int:
    validator = load_validator()
    files = collect_files(sys.argv[1:])

    if not files:
        print("No JSON files found.")
        return 0

    error_count = 0
    seen_titles: dict[str, Path] = {}

    for path in files:
        record, errors, warnings = check_file(path, validator)
        for message in errors:
            print(f"ERROR {path.name}: {message}")
        for message in warnings:
            print(f"warn  {path.name}: {message}")
        error_count += len(errors)
        if record is None or errors:
            continue

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

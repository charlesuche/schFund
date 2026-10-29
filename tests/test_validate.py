"""Tests for scripts/validate.py: the v2.2 schema and the rule checks."""

import copy
import json
from pathlib import Path

import pytest

import validate

REPO_ROOT = Path(__file__).resolve().parent.parent


def schema_errors(record: dict) -> list[str]:
    messages = []
    for err in validate.load_validator().iter_errors(record):
        messages.append(err.message)
    return messages


@pytest.fixture
def record() -> dict:
    # Banach uses every v2.2 field, so it makes a good valid starting point.
    path = REPO_ROOT / "data" / "records" / "nawa-banach-2026.json"
    return json.loads(path.read_text(encoding="utf-8"))


def all_record_files() -> list[Path]:
    files = []
    for folder in validate.DEFAULT_FOLDERS:
        for path in sorted(folder.glob("*.json")):
            files.append(path)
    return files


@pytest.mark.parametrize("path", all_record_files(), ids=lambda p: f"{p.parent.name}/{p.name}")
def test_every_record_passes_schema_and_rules(path: Path):
    record = json.loads(path.read_text(encoding="utf-8"))
    assert schema_errors(record) == []
    errors, _warnings = validate.check_rules(record)
    assert errors == []


def test_valid_record_has_no_rule_errors(record):
    errors, _warnings = validate.check_rules(record)
    assert errors == []


def test_next_cycle_confidence_must_be_unknown_without_a_date(record):
    record["application_timeline"]["next_cycle_expected"] = None
    record["application_timeline"]["next_cycle_confidence"] = "likely"
    errors, _warnings = validate.check_rules(record)
    assert "next_cycle_confidence must be 'unknown' when next_cycle_expected is null" in errors


def test_next_cycle_confidence_can_be_likely_with_a_date(record):
    record["application_timeline"]["next_cycle_expected"] = "2027-04"
    record["application_timeline"]["next_cycle_confidence"] = "likely"
    errors, _warnings = validate.check_rules(record)
    assert errors == []


def test_degree_window_must_not_be_backwards(record):
    record["eligibility_criteria"]["degree_completed_earliest"] = "2026-08-01"
    record["eligibility_criteria"]["degree_completed_latest"] = "2026-07-15"
    errors, _warnings = validate.check_rules(record)
    assert "degree_completed_earliest is after degree_completed_latest" in errors


@pytest.mark.parametrize("bad_percent", [-1, 100.5, 250])
def test_grade_percent_out_of_range_is_an_error(record, bad_percent):
    record["eligibility_criteria"]["min_grade_percent"] = bad_percent
    errors, _warnings = validate.check_rules(record)
    assert "min_grade_percent must be between 0 and 100" in errors
    assert schema_errors(record) != []


@pytest.mark.parametrize("good_percent", [0, 71.4, 100, None])
def test_grade_percent_in_range_is_fine(record, good_percent):
    record["eligibility_criteria"]["min_grade_percent"] = good_percent
    errors, _warnings = validate.check_rules(record)
    assert errors == []


def test_documents_must_be_objects(record):
    record["required_documents"] = ["Passport"]
    assert schema_errors(record) != []


def test_document_needs_optional_flag(record):
    del record["required_documents"][0]["optional"]
    assert schema_errors(record) != []


def test_source_needs_title(record):
    del record["source_urls"][0]["title"]
    assert schema_errors(record) != []


def test_award_stats_may_be_null(record):
    record["award_stats"] = None
    assert schema_errors(record) == []


def test_award_stats_needs_a_year(record):
    record["award_stats"] = {"awards": 10, "applicants": None}
    assert schema_errors(record) != []


def test_empty_selection_criteria_is_allowed(record):
    record["selection_criteria"] = {"criteria": [], "pass_rule": None}
    assert schema_errors(record) == []


def test_unknown_next_cycle_confidence_value_is_rejected(record):
    broken = copy.deepcopy(record)
    broken["application_timeline"]["next_cycle_confidence"] = "maybe"
    assert schema_errors(broken) != []


def logo(file: str = "nawa.svg") -> dict:
    return {"file": file, "source_url": "https://nawa.gov.pl/press", "added_on": "2026-10-29"}


def test_provider_logo_is_optional(record):
    record.pop("provider_logo", None)
    assert schema_errors(record) == []
    record["provider_logo"] = None
    assert schema_errors(record) == []
    assert validate.check_rules(record)[0] == []


def test_provider_logo_needs_all_three_fields(record):
    record["provider_logo"] = {"file": "nawa.svg"}
    assert schema_errors(record) != []


def test_provider_logo_file_name_is_a_plain_image_name(record):
    for bad in ["../secret.svg", "nawa.gif", "Nawa Logo.svg", "logos/nawa.svg"]:
        record["provider_logo"] = logo(bad)
        assert schema_errors(record) != [], bad


def test_provider_logo_source_must_be_https(record):
    record["provider_logo"] = {**logo(), "source_url": "http://nawa.gov.pl/press"}
    assert schema_errors(record) != []


def test_missing_logo_file_is_an_error(record, tmp_path, monkeypatch):
    monkeypatch.setattr(validate, "LOGOS_DIR", tmp_path)
    record["provider_logo"] = logo()
    assert schema_errors(record) == []
    errors, _ = validate.check_rules(record)
    assert errors == ["provider_logo file app/static/logos/nawa.svg does not exist"]


def test_present_logo_file_passes_and_big_file_warns(record, tmp_path, monkeypatch):
    monkeypatch.setattr(validate, "LOGOS_DIR", tmp_path)
    record["provider_logo"] = logo()
    (tmp_path / "nawa.svg").write_text("<svg xmlns='http://www.w3.org/2000/svg'/>")
    errors, warnings = validate.check_rules(record)
    assert errors == [] and not any("provider_logo" in w for w in warnings)

    (tmp_path / "nawa.svg").write_bytes(b"x" * (validate.LOGO_MAX_BYTES + 1))
    errors, warnings = validate.check_rules(record)
    assert errors == [] and any("optimise" in w for w in warnings)

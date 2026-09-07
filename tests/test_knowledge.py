"""KNOWLEDGE validation, and the deliberate gaps the scenarios depend on."""

import copy

import pytest
import yaml

from dentaldesk.knowledge import KnowledgeError, load_clinic, validate


@pytest.fixture
def raw(repo_root):
    path = repo_root / "knowledge" / "clinics" / "demo-smile-westlands.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_fixture_clinic_is_valid(clinic):
    assert clinic.clinic_id == "demo-smile-westlands"
    assert not clinic.warnings


def test_fixture_is_marked_fictional(clinic):
    """Spec §10 step 3 builds against a fictional clinic; it must never ship."""
    assert clinic.fictional
    assert "FICTIONAL" in clinic.get("payment.mpesa.note", "").upper()


# -- the gaps scenarios 23 and 28 depend on ---------------------------------


def test_jubilee_stays_out_of_knowledge(clinic):
    """Scenario 23 tests an insurer that is NOT in KNOWLEDGE. Do not add Jubilee."""
    assert "jubilee" not in {i.lower() for i in clinic.insurers_accepted}


def test_dentist_roster_stays_out_of_knowledge(clinic):
    """Scenario 28 tests a fact that is NOT in KNOWLEDGE. Do not add a roster."""
    assert clinic.is_unknown("dentist_roster_by_day")
    assert clinic.get("dentist_roster") is None


# -- validator rejects unsafe KNOWLEDGE -------------------------------------


def test_casualty_must_be_named_with_its_road(raw):
    bad = copy.deepcopy(raw)
    del bad["emergency"]["casualty"]["road"]
    errors, _ = validate(bad)
    assert any("emergency.casualty.road" in e for e in errors)


def test_casualty_must_be_human_verified(raw):
    bad = copy.deepcopy(raw)
    del bad["emergency"]["casualty"]["verified_on"]
    errors, _ = validate(bad)
    assert any("verified_on" in e for e in errors)


def test_emergency_numbers_must_include_999_and_112(raw):
    bad = copy.deepcopy(raw)
    bad["emergency"]["emergency_numbers"] = ["999"]
    errors, _ = validate(bad)
    assert any("999 and 112" in e for e in errors)


def test_implant_may_never_be_marked_quotable(raw):
    bad = copy.deepcopy(raw)
    for entry in bad["price_list"]:
        if entry["procedure"] == "Dental implant":
            entry["quotable"] = True
            entry["from_price_kes"] = 120000
    errors, _ = validate(bad)
    assert any("may never be quotable" in e for e in errors)


def test_loader_forces_never_quotable_categories_off(raw, tmp_path):
    """Even if a file claims otherwise, the loaded Price must not be quotable."""
    sneaky = copy.deepcopy(raw)
    for entry in sneaky["price_list"]:
        if entry["procedure"] == "Clear aligners":
            entry["quotable"] = True
            entry["from_price_kes"] = 150000
    path = tmp_path / "sneaky.yaml"
    path.write_text(yaml.safe_dump(sneaky), encoding="utf-8")
    clinic = load_clinic(path, strict=False)
    assert clinic.price("Clear aligners").quotable is False
    assert 150000 not in clinic.quotable_amounts


def test_quotable_entries_need_a_from_price(raw):
    bad = copy.deepcopy(raw)
    for entry in bad["price_list"]:
        if entry["procedure"] == "Composite filling":
            del entry["from_price_kes"]
    errors, _ = validate(bad)
    assert any("from_price_kes" in e for e in errors)


def test_sha_may_not_be_listed_as_accepted(raw):
    bad = copy.deepcopy(raw)
    bad["payment"]["insurers_accepted"].append("SHA")
    errors, _ = validate(bad)
    assert any("SHA" in e for e in errors)


def test_missing_insurer_list_is_an_error_but_empty_is_fine(raw):
    bad = copy.deepcopy(raw)
    del bad["payment"]["insurers_accepted"]
    errors, _ = validate(bad)
    assert any("insurers_accepted" in e for e in errors)

    empty = copy.deepcopy(raw)
    empty["payment"]["insurers_accepted"] = []
    errors, _ = validate(empty)
    assert not any("insurers_accepted" in e for e in errors)


def test_unoffered_service_needs_a_referral(raw):
    bad = copy.deepcopy(raw)
    del bad["services_not_offered"][0]["referral"]
    errors, _ = validate(bad)
    assert any("referral" in e for e in errors)


def test_every_day_needs_opening_hours(raw):
    bad = copy.deepcopy(raw)
    del bad["opening_hours"]["saturday"]
    errors, _ = validate(bad)
    assert any("opening_hours.saturday" in e for e in errors)


def test_consultation_fee_must_exist(raw):
    bad = copy.deepcopy(raw)
    for entry in bad["price_list"]:
        entry.pop("is_consultation_fee", None)
    errors, _ = validate(bad)
    assert any("is_consultation_fee" in e for e in errors)


def test_strict_load_refuses_an_invalid_clinic(raw, tmp_path):
    bad = copy.deepcopy(raw)
    del bad["emergency"]["casualty"]["name"]
    path = tmp_path / "bad.yaml"
    path.write_text(yaml.safe_dump(bad), encoding="utf-8")
    with pytest.raises(KnowledgeError):
        load_clinic(path)

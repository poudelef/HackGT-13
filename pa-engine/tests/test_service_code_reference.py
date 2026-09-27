"""Service-code reference matching for EOC benefit categories."""

from app.ingest.service_code_reference import load_reference, match_category, normalize_label


def test_normalize_and_match_mri_and_ambulance():
    ref = load_reference()
    cats = ref["categories"]
    mri = match_category(
        "Outpatient diagnostic tests - radiological diagnostic services (CT, 6 MRI, PET, etc.)",
        cats,
    )
    assert mri is not None
    assert "72148" in (mri.get("codes") or [])

    amb = match_category("Ambulance services", cats)
    assert amb is not None
    assert amb["codes"] == ["A0429"]

    acu = match_category("Acupuncture for chronic low back", cats)
    assert acu is not None
    assert acu["codes"] == ["97810"]


def test_reference_has_ninety_categories():
    ref = load_reference()
    assert len(ref["categories"]) == 90
    with_codes = [c for c in ref["categories"] if c.get("codes")]
    assert len(with_codes) >= 80

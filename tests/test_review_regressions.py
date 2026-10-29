"""Cases identified by the second review, separate from the original fixtures."""
from decimal import Decimal

import pytest

from src.agents.document_extraction import make_extraction_node
from src.document_extraction import extract_w2
from src.document_extraction.ocr import Token
from tests.test_extraction import ROOT, clean_tokens, parse, token, real_ocr


@pytest.mark.parametrize("text", ["2024.00", "2025.00", "2026.00", "2024"])
def test_monetary_year_like_value_is_not_tax_year(text):
    tokens = [Token(text, t.confidence, t.bbox) if t.text == "38,750.25" else t for t in clean_tokens()]
    result = parse(tokens)
    assert result.ready, result.issues
    assert result.record.tax_year.value == "2025"
    assert result.record.tax_year.source.raw_text == "2025"
    assert result.record.amounts["1"].value == Decimal(text)


@pytest.mark.parametrize("ssn", ["901-12-2024", "901-12-2025", "999-99-2026"])
def test_synthetic_ssn_suffix_is_not_tax_year(ssn):
    result = parse([Token(ssn, t.confidence, t.bbox) if t.text == "901-12-3456" else t for t in clean_tokens()])
    assert result.ready, result.issues
    assert result.record.tax_year.value == "2025"
    assert result.record.employee_ssn.value == ssn


@pytest.mark.parametrize("amount", ["123456789", "123456789.00", "901123456.00"])
def test_large_printed_amount_is_not_an_ssn(amount):
    result = parse([Token(amount, t.confidence, t.bbox) if t.text == "38,750.25" else t for t in clean_tokens()])
    assert result.ready, result.issues
    assert result.record.employee_ssn.value == "901-12-3456"
    assert result.record.amounts["1"].value == Decimal(amount)


def test_unsafe_formatted_ssn_inside_amount_region_is_still_rejected():
    result = parse([Token("123-45-6789", t.confidence, t.bbox)
                    if t.text == "38,750.25" else t for t in clean_tokens()])
    assert result.status == "rejected" and result.record is None


def test_money_never_supplies_a_missing_year():
    tokens = [Token("2025.00", t.confidence, t.bbox) if t.text == "38,750.25" else t
              for t in clean_tokens() if t.text != "2025"]
    result = parse(tokens)
    assert result.status == "needs_review"
    assert result.record.tax_year is None
    assert any(i.code == "missing_field" and i.field == "tax_year" for i in result.issues)


@pytest.mark.parametrize("value", ["1O0.00", "-100.00", "12,34.00", "O.OO", "ABC"])
def test_unreadable_optional_amount_is_not_treated_as_blank(value):
    result = parse(clean_tokens() + [token(value, 410, 150, width=130)])
    assert result.status == "needs_review"
    assert "3" not in result.record.amounts
    assert any(i.code == "invalid_amount" and i.field == "box_3" for i in result.issues)


def test_valid_and_unreadable_amount_in_one_box_is_ambiguous():
    result = parse(clean_tokens() + [token("1O0.00", 410, 96, width=130)])
    assert result.status == "needs_review"
    assert "1" not in result.record.amounts


def test_distant_number_not_consumed_when_lower_box_label_is_missing():
    tokens = [t for t in clean_tokens() if t.text not in {
        "3 Social security wages", "4 Social security tax withheld", "3,125.50"}]
    result = parse(tokens + [token("999.00", 810, 300, width=130)])
    assert result.status == "needs_review"
    assert "2" not in result.record.amounts


def test_wrapped_label_word_is_not_an_unreadable_optional_amount():
    result = parse(clean_tokens() + [token("wages", 410, 145, width=80)])
    assert result.ready


def test_masked_or_absent_identifiers_do_not_require_more_pii():
    tokens = [t for t in clean_tokens() if t.text not in {"901-12-3456", "12-3456789"}]
    result = parse(tokens + [token("XXX-XX-XXXX", 0, 40)])
    assert result.ready
    assert result.record.employee_ssn is None and result.record.employer_ein is None


def test_multiple_space_unsafe_ssn_is_rejected_without_echoing():
    result = parse(clean_tokens() + [token("123  45  6789", 0, 400)])
    assert result.status == "rejected"
    assert result.record is None
    assert "6789" not in result.model_dump_json()


def test_ocr_initialization_error_reaches_caller():
    def broken_factory():
        raise RuntimeError("model file unavailable")

    with pytest.raises(RuntimeError, match="model file unavailable"):
        make_extraction_node(broken_factory)({"document": {
            "document_id": "init-failure", "path": str(ROOT/"demo/w2_clean.jpg")}})


def test_ocr_read_error_reaches_caller():
    class BrokenReader:
        name = "test"

        def read(self, image):
            raise RuntimeError("failed inference")

    with pytest.raises(RuntimeError, match="failed inference"):
        extract_w2(ROOT/"demo/w2_clean.jpg", "read-failure", engine=BrokenReader())


@pytest.mark.ocr
@pytest.mark.parametrize("wages,ssn", [("2,024.00", "901-12-2024"), ("2026.00", "999-99-2026")])
def test_year_regressions_from_real_image_pixels(real_ocr, tmp_path, wages, ssn):
    from data.generate_fixtures import make_w2
    path = tmp_path/"year-edge.jpg"
    make_w2(path, wages=wages, ssn=ssn)
    result = extract_w2(path, "year-edge", engine=real_ocr)
    assert result.ready, result.issues
    assert result.record.tax_year.value == "2025"
    assert result.record.amounts["1"].value == Decimal(wages.replace(",", ""))


@pytest.mark.ocr
def test_unreadable_optional_amount_from_real_pixels(real_ocr, tmp_path):
    from data.generate_fixtures import make_w2
    path = tmp_path/"unreadable.jpg"
    make_w2(path, other_wages="ABC")
    result = extract_w2(path, "unreadable", engine=real_ocr)
    assert result.status == "needs_review"
    assert any(i.code == "invalid_amount" and i.field == "box_3" for i in result.issues)


@pytest.mark.ocr
def test_masked_identifiers_from_real_pixels(real_ocr, tmp_path):
    from data.generate_fixtures import make_w2
    path = tmp_path/"masked.jpg"
    make_w2(path, ssn="XXX-XX-XXXX", ein="")
    result = extract_w2(path, "masked", engine=real_ocr)
    assert result.ready, result.issues
    assert result.record.employee_ssn is None and result.record.employer_ein is None

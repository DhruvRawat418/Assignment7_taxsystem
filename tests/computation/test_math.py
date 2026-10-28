from decimal import Decimal

import pytest

from src.tools.computation_math import (
    difference, income_tax, senior_deduction, social_security_taxable, standard_deduction, sum_amounts,
)


def profile(status="single", **overrides):
    data = {"filing_status": status, "taxpayer_65_or_older": True,
            "taxpayer_blind": False, "spouse_65_or_older": False, "spouse_blind": False}
    if status == "mfs":
        data["mfs_lived_with_spouse"] = False
    return {**data, **overrides}


@pytest.mark.parametrize("status,expected", [
    ("single", "17750.00"), ("mfj", "33100.00"), ("mfs", "17350.00"),
    ("hoh", "25625.00"), ("qss", "33100.00"),
])
def test_standard_deduction_all_filing_statuses(status, expected):
    assert standard_deduction(profile(status))["value"] == expected


def test_standard_deduction_four_boxes_and_mfs_approval():
    p = profile("mfj", taxpayer_blind=True, spouse_65_or_older=True, spouse_blind=True)
    result = standard_deduction(p)
    assert result["value"] == "37900.00"
    assert result["details"]["boxes"] == 4
    with pytest.raises(ValueError):
        standard_deduction(profile("mfs", spouse_65_or_older=True))
    assert standard_deduction(profile("mfs", spouse_65_or_older=True,
                                      mfs_spouse_allowance_approved=True))["value"] == "18950.00"


@pytest.mark.parametrize("status,agi,spouse,expected", [
    ("single", "75000", False, "6000.00"),
    ("single", "75001", False, "5999.94"),
    ("single", "85000", False, "5400.00"),
    ("single", "175000", False, "0.00"),
    ("mfj", "150000", True, "12000.00"),
    ("mfj", "160000", True, "10800.00"),
    ("mfj", "250000", True, "0.00"),
    ("mfs", "10000", False, "0.00"),
    ("qss", "85000", False, "5400.00"),
])
def test_enhanced_deduction_phaseout_is_per_person(status, agi, spouse, expected):
    assert senior_deduction(agi, profile(status, spouse_65_or_older=spouse))["value"] == expected


@pytest.mark.parametrize("status,other,benefits,expected", [
    ("single", "15000", "20000", "0.00"),  # provisional income exactly 25,000
    ("single", "15001", "20000", "0.50"),
    ("single", "24000", "20000", "4500.00"),  # second threshold
    ("single", "30000", "20000", "9600.00"),
    ("single", "100000", "20000", "17000.00"),  # 85% cap
    ("mfj", "22000", "20000", "0.00"),
    ("mfj", "34000", "20000", "6000.00"),
    ("qss", "30000", "20000", "9600.00"),
    ("mfs", "30000", "20000", "9600.00"),
])
def test_social_security_thresholds(status, other, benefits, expected):
    assert social_security_taxable(benefits, other, "0", "0", profile(status))["value"] == expected


def test_social_security_uses_exempt_interest_adjustments_and_mfs_living_status():
    assert social_security_taxable("20000", "15000", "2000", "0", profile())["value"] == "1000.00"
    assert social_security_taxable("20000", "15000", "2000", "2000", profile())["value"] == "0.00"
    assert social_security_taxable("100", "0", "0", "0",
        profile("mfs", mfs_lived_with_spouse=True))["value"] == "42.50"


@pytest.mark.parametrize("status,income,expected", [
    ("single", "11925", "1192.50"), ("single", "48475", "5578.50"),
    ("single", "103350", "17651.00"), ("single", "626350", "188769.75"),
    ("mfj", "96950", "11157.00"), ("qss", "96950", "11157.00"),
    ("hoh", "250500", "55484.00"), ("mfs", "375800", "101077.25"),
])
def test_2025_rate_schedule_boundaries(status, income, expected):
    assert income_tax(income, "0", status)["value"] == expected


def test_qualified_dividends_are_not_double_counted_or_taxed_as_ordinary_income():
    assert income_tax("100000", "10000", "single")["value"] == "16214.00"
    assert income_tax("48350", "10000", "single")["value"] == "4363.50"
    assert income_tax("1000", "2000", "single")["value"] == "0.00"
    result = income_tax("700000", "700000", "single")
    assert result["details"]["dividends_at_zero"] == "48350.00"
    assert result["details"]["dividends_at_fifteen"] == "485050.00"
    assert result["details"]["dividends_at_twenty"] == "166600.00"


def test_decimal_precision_and_explicit_zero_floors():
    assert sum_amounts(["0.10", "0.20"])["value"] == "0.30"
    assert difference("10", "20")["value"] == "-10.00"
    assert difference("10", "20", True)["value"] == "0.00"
    with pytest.raises(ValueError):
        sum_amounts([])
    for bad in ("NaN", "Infinity", "1.001", 1.1, True):
        with pytest.raises(ValueError):
            sum_amounts([bad])

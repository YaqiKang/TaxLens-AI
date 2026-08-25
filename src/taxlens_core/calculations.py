from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from .models import AssessmentParameters, AssetRecord, CalculationResult

CENT = Decimal("0.01")


def money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def policy_basis_total(asset: AssetRecord) -> Decimal:
    if asset.unit_tax_basis is None or asset.quantity is None:
        raise ValueError("unit_tax_basis and quantity are required")
    return money(asset.unit_tax_basis * Decimal(asset.quantity))


def _first_day_next_month(value: date) -> date:
    if value.month == 12:
        return date(value.year + 1, 1, 1)
    return date(value.year, value.month + 1, 1)


def _add_months(value: date, months: int) -> date:
    index = value.year * 12 + value.month - 1 + months
    return date(index // 12, index % 12 + 1, 1)


def _month_count(start: date, end: date) -> int:
    if start > end:
        return 0
    return (end.year - start.year) * 12 + end.month - start.month + 1


def current_year_accounting_depreciation(
    asset: AssetRecord,
    parameters: AssessmentParameters,
) -> tuple[Decimal, str, int | None]:
    if asset.current_year_accounting_depreciation is not None:
        return money(asset.current_year_accounting_depreciation), "provided", None
    if asset.placed_in_service_date is None or asset.accounting_useful_life_years is None:
        raise ValueError("placed_in_service_date and accounting_useful_life_years are required")

    basis = policy_basis_total(asset)
    residual_rate = (
        asset.residual_rate_percent
        if asset.residual_rate_percent is not None
        else parameters.default_residual_rate_percent
    )
    start = _first_day_next_month(asset.placed_in_service_date)
    total_months = max(
        1,
        int((asset.accounting_useful_life_years * Decimal("12")).to_integral_value(rounding=ROUND_HALF_UP)),
    )
    end_of_life = _add_months(start, total_months - 1)
    assessment_start = date(parameters.assessment_year, 1, 1)
    assessment_end = min(parameters.cutoff_date, date(parameters.assessment_year, 12, 31))
    effective_start = max(start, assessment_start)
    effective_end = min(end_of_life, assessment_end)
    months = _month_count(effective_start, effective_end)
    monthly_depreciation = basis * (Decimal("1") - residual_rate / Decimal("100")) / Decimal(total_months)
    return money(monthly_depreciation * Decimal(months)), "calculated_straight_line", months


def calculate_policy_impact(asset: AssetRecord, parameters: AssessmentParameters) -> CalculationResult:
    basis = policy_basis_total(asset)
    accounting_depreciation, source, months = current_year_accounting_depreciation(asset, parameters)
    one_time_deduction = basis
    difference = money(one_time_deduction - accounting_depreciation)
    timing_impact = money(difference * parameters.cit_rate_percent / Decimal("100"))
    return CalculationResult(
        policy_basis_total=basis,
        accounting_depreciation=accounting_depreciation,
        one_time_tax_deduction=one_time_deduction,
        tax_accounting_difference=difference,
        cit_timing_impact=timing_impact,
        depreciation_source=source,
        accounting_depreciation_months=months,
    )


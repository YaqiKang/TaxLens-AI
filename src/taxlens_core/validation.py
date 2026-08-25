from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from .constants import (
    ACQUISITION_METHODS,
    BUILDING_FLAGS,
    CLAIMED_FLAGS,
    CONDITIONAL_DATE_FIELD,
    EVIDENCE_STATUSES,
    SUPPORTED_ASSESSMENT_YEARS,
    SUPPORTED_DEPRECIATION_METHOD,
)
from .models import AssessmentParameters, AssetRecord, IssueSeverity, ValidationIssue


def _blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _text(value: Any) -> str | None:
    return None if _blank(value) else str(value).strip()


def _decimal(value: Any) -> Decimal | None:
    if _blank(value):
        return None
    try:
        return Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, ValueError):
        return None


def _date(value: Any) -> date | None:
    if _blank(value):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value).strip())
    except ValueError:
        return None


def validate_parameters(parameters: AssessmentParameters) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if parameters.assessment_year not in SUPPORTED_ASSESSMENT_YEARS:
        issues.append(ValidationIssue(
            "UNSUPPORTED_ASSESSMENT_YEAR_REQUIRES_POLICY_CONFIRMATION",
            "当前MVP仅支持2026评估年度；其他扣除所属年度需进一步确认政策边界后再启用",
            IssueSeverity.ERROR,
        ))
    if not Decimal("0") <= parameters.cit_rate_percent <= Decimal("100"):
        issues.append(ValidationIssue(
            "INVALID_CIT_RATE", "cit_rate_percent 必须在 0–100", IssueSeverity.ERROR
        ))
    if parameters.cutoff_date.year < parameters.assessment_year:
        issues.append(ValidationIssue(
            "INVALID_CUTOFF_DATE", "cutoff_date 不得早于评估年度", IssueSeverity.ERROR
        ))
    if not Decimal("0") <= parameters.default_residual_rate_percent <= Decimal("10"):
        issues.append(ValidationIssue(
            "INVALID_DEFAULT_RESIDUAL_RATE",
            "default_residual_rate_percent 必须在 0–10",
            IssueSeverity.ERROR,
        ))
    return issues


def validate_and_normalize_record(raw: dict[str, Any]) -> tuple[AssetRecord, list[ValidationIssue]]:
    row = int(raw.get("_row_number", 0))
    issues: list[ValidationIssue] = []

    def error(code: str, message: str, field: str) -> None:
        issues.append(ValidationIssue(code, message, IssueSeverity.ERROR, row, field))

    text_fields = {
        name: _text(raw.get(name))
        for name in [
            "asset_id", "asset_name", "asset_description", "fixed_asset_category",
            "acquisition_method", "building_flag", "depreciation_method",
            "policy_already_claimed", "evidence_status", "note",
        ]
    }
    for field in [
        "asset_id", "asset_name", "asset_description", "fixed_asset_category",
        "acquisition_method", "building_flag", "depreciation_method",
        "policy_already_claimed", "evidence_status",
    ]:
        if text_fields[field] is None:
            error("MISSING_REQUIRED_FIELD", f"{field} 为必填字段", field)

    length_limits = {"asset_name": 100, "asset_description": 500, "note": 500}
    for field, limit in length_limits.items():
        value = text_fields[field]
        if value is not None and len(value) > limit:
            error("TEXT_TOO_LONG", f"{field} 不得超过 {limit} 个字符", field)

    acquisition_method = text_fields["acquisition_method"]
    if acquisition_method is not None and acquisition_method not in ACQUISITION_METHODS:
        error("INVALID_ENUM", "acquisition_method 枚举值无效", "acquisition_method")
    if text_fields["building_flag"] is not None and text_fields["building_flag"] not in BUILDING_FLAGS:
        error("INVALID_ENUM", "building_flag 枚举值无效", "building_flag")
    if text_fields["policy_already_claimed"] is not None and text_fields["policy_already_claimed"] not in CLAIMED_FLAGS:
        error("INVALID_ENUM", "policy_already_claimed 枚举值无效", "policy_already_claimed")
    if text_fields["evidence_status"] is not None and text_fields["evidence_status"] not in EVIDENCE_STATUSES:
        error("INVALID_ENUM", "evidence_status 枚举值无效", "evidence_status")
    if text_fields["depreciation_method"] is not None and text_fields["depreciation_method"] != SUPPORTED_DEPRECIATION_METHOD:
        error("UNSUPPORTED_DEPRECIATION_METHOD", "MVP 仅支持直线法", "depreciation_method")

    parsed_dates: dict[str, date | None] = {}
    for field in [
        "invoice_date", "arrival_date", "completion_settlement_date", "placed_in_service_date"
    ]:
        parsed_dates[field] = _date(raw.get(field))
        if not _blank(raw.get(field)) and parsed_dates[field] is None:
            error("INVALID_DATE", f"{field} 必须为有效日期", field)
    if parsed_dates["placed_in_service_date"] is None:
        error("MISSING_REQUIRED_FIELD", "placed_in_service_date 为必填字段", "placed_in_service_date")

    if acquisition_method in CONDITIONAL_DATE_FIELD:
        conditional_field = CONDITIONAL_DATE_FIELD[acquisition_method]
        if parsed_dates[conditional_field] is None:
            error(
                "MISSING_CONDITIONAL_DATE",
                f"{acquisition_method} 必须填写 {conditional_field}",
                conditional_field,
            )
        elif (
            parsed_dates["placed_in_service_date"] is not None
            and parsed_dates["placed_in_service_date"] < parsed_dates[conditional_field]
        ):
            error(
                "SERVICE_BEFORE_ACQUISITION",
                "placed_in_service_date 不得早于规则确定的购置日期",
                "placed_in_service_date",
            )

    unit_tax_basis = _decimal(raw.get("unit_tax_basis"))
    if unit_tax_basis is None:
        error("INVALID_AMOUNT", "unit_tax_basis 必须为有效金额", "unit_tax_basis")
    elif unit_tax_basis <= 0:
        error("INVALID_AMOUNT", "unit_tax_basis 必须大于 0", "unit_tax_basis")

    quantity_decimal = _decimal(raw.get("quantity"))
    quantity: int | None = None
    if quantity_decimal is None or quantity_decimal != quantity_decimal.to_integral_value():
        error("INVALID_QUANTITY", "quantity 必须为正整数", "quantity")
    else:
        quantity = int(quantity_decimal)
        if quantity <= 0:
            error("INVALID_QUANTITY", "quantity 必须为正整数", "quantity")

    useful_life = _decimal(raw.get("accounting_useful_life_years"))
    if useful_life is None or useful_life <= 0:
        error(
            "INVALID_USEFUL_LIFE",
            "accounting_useful_life_years 必须大于 0",
            "accounting_useful_life_years",
        )

    residual_rate = _decimal(raw.get("residual_rate"))
    if residual_rate is not None and not Decimal("0") <= residual_rate <= Decimal("10"):
        error("INVALID_RESIDUAL_RATE", "residual_rate 必须在 0–10", "residual_rate")

    provided_depreciation = _decimal(raw.get("current_year_accounting_depreciation"))
    if not _blank(raw.get("current_year_accounting_depreciation")):
        if provided_depreciation is None or provided_depreciation < 0:
            error(
                "INVALID_ACCOUNTING_DEPRECIATION",
                "current_year_accounting_depreciation 必须大于等于 0",
                "current_year_accounting_depreciation",
            )

    return AssetRecord(
        row_number=row,
        asset_id=text_fields["asset_id"],
        asset_name=text_fields["asset_name"],
        asset_description=text_fields["asset_description"],
        fixed_asset_category=text_fields["fixed_asset_category"],
        acquisition_method=acquisition_method,
        invoice_date=parsed_dates["invoice_date"],
        arrival_date=parsed_dates["arrival_date"],
        completion_settlement_date=parsed_dates["completion_settlement_date"],
        placed_in_service_date=parsed_dates["placed_in_service_date"],
        unit_tax_basis=unit_tax_basis,
        quantity=quantity,
        building_flag=text_fields["building_flag"],
        accounting_useful_life_years=useful_life,
        residual_rate_percent=residual_rate,
        depreciation_method=text_fields["depreciation_method"],
        current_year_accounting_depreciation=provided_depreciation,
        policy_already_claimed=text_fields["policy_already_claimed"],
        evidence_status=text_fields["evidence_status"],
        note=text_fields["note"],
    ), issues

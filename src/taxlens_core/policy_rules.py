from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .constants import (
    AMBIGUOUS_CATEGORIES,
    BUILDING_CATEGORIES,
    CONDITIONAL_DATE_FIELD,
    POLICY_ACQUISITION_END,
    POLICY_ACQUISITION_START,
    STRONG_BUILDING_KEYWORDS,
    UNIT_TAX_BASIS_THRESHOLD,
)
from .models import AssessmentParameters, AssessmentStatus, AssetRecord, ValidationIssue


@dataclass(frozen=True)
class RuleDecision:
    status: AssessmentStatus
    reason_codes: list[str]
    reason_messages: list[str]
    acquisition_date: date | None
    deduction_year: int | None


def derive_acquisition_date(asset: AssetRecord) -> date | None:
    field = CONDITIONAL_DATE_FIELD.get(asset.acquisition_method or "")
    return getattr(asset, field) if field else None


def derive_deduction_year(placed_in_service_date: date | None) -> int | None:
    if placed_in_service_date is None:
        return None
    return placed_in_service_date.year + (1 if placed_in_service_date.month == 12 else 0)


def _has_text_classification_conflict(asset: AssetRecord) -> bool:
    # Name/description keywords are weak review signals only. They never set
    # building_flag and never produce an automatic tax eligibility conclusion.
    name_and_description = f"{asset.asset_name or ''} {asset.asset_description or ''}"
    category_is_building = asset.fixed_asset_category in BUILDING_CATEGORIES
    text_mentions_building = any(
        keyword in name_and_description for keyword in STRONG_BUILDING_KEYWORDS
    )
    return (
        (asset.building_flag == "否" and (category_is_building or text_mentions_building))
        or (asset.building_flag == "是" and asset.fixed_asset_category not in BUILDING_CATEGORIES)
    )


def evaluate_policy(
    asset: AssetRecord,
    parameters: AssessmentParameters,
    validation_issues: list[ValidationIssue],
) -> RuleDecision:
    acquisition_date = derive_acquisition_date(asset)
    deduction_year = derive_deduction_year(asset.placed_in_service_date)

    # PRD priority: 待补充 > 需人工复核 > 不适用 > 可选择适用.
    if validation_issues:
        return RuleDecision(
            AssessmentStatus.NEEDS_INFORMATION,
            [issue.code for issue in validation_issues],
            [issue.message for issue in validation_issues],
            acquisition_date,
            deduction_year,
        )

    review_codes: list[str] = []
    review_messages: list[str] = []
    if asset.building_flag == "不确定" or asset.fixed_asset_category in AMBIGUOUS_CATEGORIES:
        review_codes.append("ASSET_NATURE_UNCERTAIN")
        review_messages.append("资产性质无法由结构化字段确定，需人工复核")
    if _has_text_classification_conflict(asset):
        review_codes.append("ASSET_CLASSIFICATION_CONFLICT")
        review_messages.append("资产类别、描述与建筑物标识存在冲突，需人工复核")
    if asset.evidence_status != "完整":
        review_codes.append("EVIDENCE_INCOMPLETE")
        review_messages.append("证据状态非完整，需人工核验证据链")
    if asset.policy_already_claimed in {"是", "不确定"}:
        review_codes.append("CLAIM_STATUS_REVIEW")
        review_messages.append("已享受状态为“是”或“不确定”，需人工排查重复享受")
    if review_codes:
        return RuleDecision(
            AssessmentStatus.NEEDS_MANUAL_REVIEW,
            review_codes,
            review_messages,
            acquisition_date,
            deduction_year,
        )

    inapplicable_codes: list[str] = []
    inapplicable_messages: list[str] = []
    if asset.building_flag == "是" or asset.fixed_asset_category in BUILDING_CATEGORIES:
        inapplicable_codes.append("BUILDING_EXCLUDED")
        inapplicable_messages.append("房屋、建筑物不属于本政策设备、器具范围")
    if asset.unit_tax_basis is not None and asset.unit_tax_basis > UNIT_TAX_BASIS_THRESHOLD:
        inapplicable_codes.append("UNIT_BASIS_OVER_THRESHOLD")
        inapplicable_messages.append("单台（套）计税基础超过 500 万元")
    if (
        acquisition_date is not None
        and not POLICY_ACQUISITION_START <= acquisition_date <= POLICY_ACQUISITION_END
    ):
        inapplicable_codes.append("ACQUISITION_OUTSIDE_POLICY_PERIOD")
        inapplicable_messages.append(
            "规则确定的购置日期不在公告2023年第37号明确的2024-01-01至2027-12-31资产购进窗口"
        )
    if deduction_year is not None and deduction_year != parameters.assessment_year:
        inapplicable_codes.append("DEDUCTION_YEAR_MISMATCH")
        inapplicable_messages.append("投用次月所属年度与当前评估年度不一致")
    if inapplicable_codes:
        return RuleDecision(
            AssessmentStatus.NOT_APPLICABLE,
            inapplicable_codes,
            inapplicable_messages,
            acquisition_date,
            deduction_year,
        )

    reason_codes = ["ALL_DETERMINISTIC_CONDITIONS_PASSED", "POLICY_CHOICE_REQUIRED"]
    reason_messages = [
        "结构化字段满足MVP确定性政策条件",
        "纳税人仍需作出是否选择适用的决定并留存资料",
    ]
    return RuleDecision(
        AssessmentStatus.POTENTIALLY_APPLICABLE,
        reason_codes,
        reason_messages,
        acquisition_date,
        deduction_year,
    )

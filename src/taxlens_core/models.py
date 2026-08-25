from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Any


class AssessmentStatus(str, Enum):
    NEEDS_INFORMATION = "待补充"
    NEEDS_MANUAL_REVIEW = "需人工复核"
    NOT_APPLICABLE = "不适用"
    POTENTIALLY_APPLICABLE = "可选择适用"


class IssueSeverity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass(frozen=True)
class AssessmentParameters:
    assessment_year: int
    cit_rate_percent: Decimal
    cutoff_date: date
    default_residual_rate_percent: Decimal


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str
    severity: IssueSeverity
    row_number: int | None = None
    field: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["severity"] = self.severity.value
        return result


@dataclass
class AssetRecord:
    row_number: int
    asset_id: str | None = None
    asset_name: str | None = None
    asset_description: str | None = None
    fixed_asset_category: str | None = None
    acquisition_method: str | None = None
    invoice_date: date | None = None
    arrival_date: date | None = None
    completion_settlement_date: date | None = None
    placed_in_service_date: date | None = None
    unit_tax_basis: Decimal | None = None
    quantity: int | None = None
    building_flag: str | None = None
    accounting_useful_life_years: Decimal | None = None
    residual_rate_percent: Decimal | None = None
    depreciation_method: str | None = None
    current_year_accounting_depreciation: Decimal | None = None
    policy_already_claimed: str | None = None
    evidence_status: str | None = None
    note: str | None = None


@dataclass(frozen=True)
class CalculationResult:
    policy_basis_total: Decimal
    accounting_depreciation: Decimal
    one_time_tax_deduction: Decimal
    tax_accounting_difference: Decimal
    cit_timing_impact: Decimal
    depreciation_source: str
    accounting_depreciation_months: int | None

    def to_dict(self) -> dict[str, Any]:
        return {
            key: (format(value, "f") if isinstance(value, Decimal) else value)
            for key, value in asdict(self).items()
        }


@dataclass
class AssetAssessment:
    row_number: int
    asset_id: str | None
    status: AssessmentStatus
    reason_codes: list[str]
    reason_messages: list[str]
    acquisition_date: date | None = None
    deduction_year: int | None = None
    calculations: CalculationResult | None = None
    validation_issues: list[ValidationIssue] = field(default_factory=list)
    review_required: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "row_number": self.row_number,
            "asset_id": self.asset_id,
            "status": self.status.value,
            "reason_codes": self.reason_codes,
            "reason_messages": self.reason_messages,
            "acquisition_date": self.acquisition_date.isoformat() if self.acquisition_date else None,
            "deduction_year": self.deduction_year,
            "calculations": self.calculations.to_dict() if self.calculations else None,
            "validation_issues": [issue.to_dict() for issue in self.validation_issues],
            "review_required": self.review_required,
        }


@dataclass
class WorkbookAssessment:
    source_file: str
    parameters: AssessmentParameters
    batch_issues: list[ValidationIssue]
    assessments: list[AssetAssessment]

    def to_dict(self) -> dict[str, Any]:
        counts = {status.value: 0 for status in AssessmentStatus}
        for item in self.assessments:
            counts[item.status.value] += 1
        return {
            "source_file": self.source_file,
            "parameters": {
                "assessment_year": self.parameters.assessment_year,
                "cit_rate_percent": format(self.parameters.cit_rate_percent, "f"),
                "cutoff_date": self.parameters.cutoff_date.isoformat(),
                "default_residual_rate_percent": format(
                    self.parameters.default_residual_rate_percent, "f"
                ),
            },
            "batch_issues": [issue.to_dict() for issue in self.batch_issues],
            "summary": {"record_count": len(self.assessments), "status_counts": counts},
            "assessments": [item.to_dict() for item in self.assessments],
            "scope_assumptions": [
                "假设有足够应纳税所得额可吸收扣除",
                "所得税影响仅表示时间性现金流影响，不表示永久节税",
                "未建模亏损、税率变动、递延所得税会计和折现",
                "不适用或需复核记录不推导常规税法折旧基线",
            ],
        }


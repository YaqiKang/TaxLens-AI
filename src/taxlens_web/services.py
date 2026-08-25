from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

from taxlens_core.excel_io import read_and_validate_workbook
from taxlens_core.models import (
    AssessmentParameters,
    AssessmentStatus,
    IssueSeverity,
    ValidationIssue,
    WorkbookAssessment,
)
from taxlens_core.pipeline import run_workbook_assessment
from taxlens_core.validation import validate_and_normalize_record, validate_parameters


MISSING_CODES = {"MISSING_REQUIRED_FIELD"}
CONDITIONAL_CODES = {"MISSING_CONDITIONAL_DATE"}
FORMAT_CODES = {
    "INVALID_DATE",
    "INVALID_AMOUNT",
    "INVALID_QUANTITY",
    "INVALID_USEFUL_LIFE",
    "INVALID_RESIDUAL_RATE",
    "INVALID_ACCOUNTING_DEPRECIATION",
    "INVALID_ENUM",
    "TEXT_TOO_LONG",
    "SERVICE_BEFORE_ACQUISITION",
    "UNSUPPORTED_DEPRECIATION_METHOD",
}


@dataclass
class DataCheckResult:
    source_path: str
    records: list[dict[str, Any]] = field(default_factory=list)
    batch_issues: list[ValidationIssue] = field(default_factory=list)
    row_issues: dict[int, list[ValidationIssue]] = field(default_factory=dict)

    @property
    def all_issues(self) -> list[ValidationIssue]:
        return self.batch_issues + [
            issue for issues in self.row_issues.values() for issue in issues
        ]

    @property
    def total_rows(self) -> int:
        return len(self.records)

    @property
    def processable_rows(self) -> int:
        return sum(1 for record in self.records if not self.row_issues.get(record["_row_number"]))

    @property
    def error_count(self) -> int:
        return sum(issue.severity == IssueSeverity.ERROR for issue in self.all_issues)

    @property
    def warning_count(self) -> int:
        return sum(issue.severity == IssueSeverity.WARNING for issue in self.all_issues)

    @property
    def can_assess(self) -> bool:
        return not any(issue.severity == IssueSeverity.ERROR for issue in self.batch_issues)

    def count_codes(self, codes: set[str]) -> int:
        return sum(issue.code in codes for issue in self.all_issues)

    def issue_rows(self) -> list[dict[str, Any]]:
        return [
            {
                "层级": "批次" if issue.row_number is None else "行级",
                "行号": issue.row_number,
                "字段": issue.field or "—",
                "问题类型": issue.code,
                "说明": issue.message,
                "级别": "错误" if issue.severity == IssueSeverity.ERROR else "警告",
            }
            for issue in self.all_issues
        ]


@dataclass(frozen=True)
class AssessmentSummary:
    record_count: int
    status_counts: dict[str, int]
    tax_accounting_difference: Decimal
    cit_timing_impact: Decimal


def check_workbook(path: str | Path, parameters: AssessmentParameters) -> DataCheckResult:
    """Run upload and row checks without making any policy determination."""
    source = str(path)
    try:
        parameter_issues = validate_parameters(parameters)
        records, workbook_issues = read_and_validate_workbook(path)
        row_issues: dict[int, list[ValidationIssue]] = {}
        for raw in records:
            _, issues = validate_and_normalize_record(raw)
            if issues:
                row_issues[int(raw["_row_number"])] = issues
        return DataCheckResult(
            source_path=source,
            records=records,
            batch_issues=[*parameter_issues, *workbook_issues],
            row_issues=row_issues,
        )
    except Exception:
        # UI resilience boundary. Do not expose a stack trace or infer data.
        return DataCheckResult(
            source_path=source,
            batch_issues=[ValidationIssue(
                "UNEXPECTED_FILE_CHECK_ERROR",
                "文件检查未完成，请确认文件未损坏并重新上传官方模板格式的.xlsx文件",
                IssueSeverity.ERROR,
            )],
        )


def assess_checked_workbook(
    check_result: DataCheckResult,
    parameters: AssessmentParameters,
) -> WorkbookAssessment:
    if not check_result.can_assess:
        raise ValueError("Batch-blocking issues must be resolved before assessment")
    return run_workbook_assessment(check_result.source_path, parameters)


def summarize_assessment(result: WorkbookAssessment) -> AssessmentSummary:
    status_counts = {status.value: 0 for status in AssessmentStatus}
    difference = Decimal("0")
    timing_impact = Decimal("0")
    for assessment in result.assessments:
        status_counts[assessment.status.value] += 1
        if assessment.calculations is not None:
            difference += assessment.calculations.tax_accounting_difference
            timing_impact += assessment.calculations.cit_timing_impact
    return AssessmentSummary(
        record_count=len(result.assessments),
        status_counts=status_counts,
        tax_accounting_difference=difference,
        cit_timing_impact=timing_impact,
    )


def build_asset_rows(
    result: WorkbookAssessment,
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    input_by_id = {str(record.get("asset_id", "")).strip(): record for record in records}
    rows: list[dict[str, Any]] = []
    for assessment in result.assessments:
        source = input_by_id.get(assessment.asset_id or "", {})
        calc = assessment.calculations
        rows.append({
            "资产ID": assessment.asset_id or "—",
            "资产名称": source.get("asset_name") or "—",
            "固定资产类别": source.get("fixed_asset_category") or "—",
            "单台（套）计税基础": source.get("unit_tax_basis"),
            "数量": source.get("quantity"),
            "购进日期": assessment.acquisition_date,
            "扣除所属年度": assessment.deduction_year,
            "状态": assessment.status.value,
            "当期税会差异": calc.tax_accounting_difference if calc else None,
            "所得税时间性影响": calc.cit_timing_impact if calc else None,
            "主要原因": "；".join(assessment.reason_messages),
        })
    return rows


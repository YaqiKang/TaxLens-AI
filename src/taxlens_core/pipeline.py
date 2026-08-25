from __future__ import annotations

from pathlib import Path

from .calculations import calculate_policy_impact
from .excel_io import read_and_validate_workbook
from .models import (
    AssessmentParameters,
    AssessmentStatus,
    AssetAssessment,
    WorkbookAssessment,
)
from .policy_rules import evaluate_policy
from .validation import validate_and_normalize_record, validate_parameters


def run_workbook_assessment(
    path: str | Path,
    parameters: AssessmentParameters,
) -> WorkbookAssessment:
    parameter_issues = validate_parameters(parameters)
    records, workbook_issues = read_and_validate_workbook(path)
    batch_issues = [*parameter_issues, *workbook_issues]
    if batch_issues:
        return WorkbookAssessment(str(path), parameters, batch_issues, [])

    assessments: list[AssetAssessment] = []
    for raw in records:
        asset, validation_issues = validate_and_normalize_record(raw)
        decision = evaluate_policy(asset, parameters, validation_issues)
        calculations = None
        if decision.status == AssessmentStatus.POTENTIALLY_APPLICABLE:
            calculations = calculate_policy_impact(asset, parameters)
        assessments.append(AssetAssessment(
            row_number=asset.row_number,
            asset_id=asset.asset_id,
            status=decision.status,
            reason_codes=decision.reason_codes,
            reason_messages=decision.reason_messages,
            acquisition_date=decision.acquisition_date,
            deduction_year=decision.deduction_year,
            calculations=calculations,
            validation_issues=validation_issues,
            review_required=decision.status == AssessmentStatus.NEEDS_MANUAL_REVIEW,
        ))
    return WorkbookAssessment(str(path), parameters, batch_issues, assessments)


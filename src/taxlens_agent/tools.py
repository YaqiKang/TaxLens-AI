from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from taxlens_core.calculations import calculate_policy_impact
from taxlens_core.constants import (
    AMBIGUOUS_CATEGORIES,
    BUILDING_CATEGORIES,
    STRONG_BUILDING_KEYWORDS,
)
from taxlens_core.models import (
    AssessmentParameters,
    AssessmentStatus,
    AssetAssessment,
    CalculationResult,
    WorkbookAssessment,
)
from taxlens_core.pipeline import run_workbook_assessment
from taxlens_core.validation import validate_and_normalize_record
from taxlens_web.services import DataCheckResult, check_workbook

from .models import (
    ClassificationSuggestion,
    ConditionCheck,
    EvidenceVerification,
    PolicyEvidence,
)
from .providers import (
    LLMInvalidOutputError,
    LLMProviderError,
    StructuredLLMProvider,
)
from .retrieval import ControlledPolicyKnowledgeBase


def _display(value: Any) -> str:
    if value is None or value == "":
        return "未提供"
    if isinstance(value, (date, Decimal)):
        return str(value)
    return str(value)


class LedgerParsingTool:
    def parse(
        self, path: str | Path, parameters: AssessmentParameters
    ) -> DataCheckResult:
        return check_workbook(path, parameters)


class DeterministicRuleTool:
    """Thin adapter: the frozen Phase 1 pipeline remains the single rule source."""

    def evaluate(
        self, path: str | Path, parameters: AssessmentParameters
    ) -> WorkbookAssessment:
        return run_workbook_assessment(path, parameters)


class TaxCalculationTool:
    """Replays the frozen calculator and verifies the pipeline result byte-for-byte by value."""

    def verify(
        self,
        assessment: WorkbookAssessment,
        records: list[dict[str, Any]],
    ) -> dict[str, CalculationResult]:
        by_row = {int(record["_row_number"]): record for record in records}
        verified: dict[str, CalculationResult] = {}
        for item in assessment.assessments:
            if item.status != AssessmentStatus.POTENTIALLY_APPLICABLE:
                continue
            asset, issues = validate_and_normalize_record(by_row[item.row_number])
            if issues:
                raise ValueError("Eligible asset unexpectedly failed frozen validation")
            replay = calculate_policy_impact(asset, assessment.parameters)
            if replay != item.calculations:
                raise ValueError("Frozen calculation replay mismatch")
            verified[item.asset_id or str(item.row_number)] = replay
        return verified


class AssetClassificationTool:
    ALLOWED_CATEGORIES = {"设备、器具候选", "房屋、建筑物候选", "无法确认"}

    def __init__(
        self,
        provider: StructuredLLMProvider,
        *,
        timeout_seconds: float = 8.0,
        confidence_threshold: float = 0.75,
    ):
        self.provider = provider
        self.timeout_seconds = timeout_seconds
        self.confidence_threshold = confidence_threshold

    @staticmethod
    def needs_assistance(raw: dict[str, Any]) -> bool:
        category = str(raw.get("fixed_asset_category") or "").strip()
        building_flag = str(raw.get("building_flag") or "").strip()
        text = f"{raw.get('asset_name') or ''} {raw.get('asset_description') or ''}"
        category_is_building = category in BUILDING_CATEGORIES
        text_mentions_building = any(keyword in text for keyword in STRONG_BUILDING_KEYWORDS)
        return (
            category in AMBIGUOUS_CATEGORIES
            or building_flag == "不确定"
            or (building_flag == "否" and (category_is_building or text_mentions_building))
            or (building_flag == "是" and not category_is_building)
        )

    def classify(self, raw: dict[str, Any]) -> ClassificationSuggestion:
        original_category = str(raw.get("fixed_asset_category") or "").strip() or None
        original_flag = str(raw.get("building_flag") or "").strip() or None
        if not self.needs_assistance(raw):
            return ClassificationSuggestion(
                called=False,
                provider_status="not_needed",
                suggested_category=original_category or "无法确认",
                confidence=1.0,
                reason="结构化资产类别与建筑物标识未触发语义辅助条件。",
                requires_human_review=False,
                original_category=original_category,
                original_building_flag=original_flag,
            )

        prompt = (
            "你只做资产性质的辅助分类，不作税务适用结论，不计算金额，不改写输入事实。"
            "只返回JSON：suggested_category（设备、器具候选/房屋、建筑物候选/无法确认）、"
            "confidence（0到1）、reason（不超过120字）、requires_human_review（布尔值）。"
        )
        try:
            output = self.provider.generate_json(
                task="asset_classification_assistance",
                system_prompt=prompt,
                payload={
                    "asset_name": raw.get("asset_name"),
                    "asset_description": raw.get("asset_description"),
                    "original_category": original_category,
                    "original_building_flag": original_flag,
                },
                timeout_seconds=self.timeout_seconds,
            )
            category, confidence, reason, requested_review = self._validate_output(output)
            conflict = (
                (original_flag == "否" and category == "房屋、建筑物候选")
                or (original_flag == "是" and category == "设备、器具候选")
            )
            return ClassificationSuggestion(
                called=True,
                provider_status="success",
                suggested_category=category,
                confidence=confidence,
                reason=reason,
                requires_human_review=(
                    requested_review or confidence < self.confidence_threshold or conflict
                ),
                original_category=original_category,
                original_building_flag=original_flag,
            )
        except LLMProviderError as exc:
            return ClassificationSuggestion(
                called=True,
                provider_status=f"degraded_{type(exc).__name__}",
                suggested_category="无法确认",
                confidence=0.0,
                reason="语义辅助不可用，未生成资产性质结论，已保留原始字段并转人工复核。",
                requires_human_review=True,
                original_category=original_category,
                original_building_flag=original_flag,
            )

    def _validate_output(self, output: dict[str, Any]) -> tuple[str, float, str, bool]:
        try:
            category = output["suggested_category"]
            confidence = float(output["confidence"])
            reason = output["reason"].strip()
            review = output["requires_human_review"]
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise LLMInvalidOutputError("资产辅助分类JSON字段无效") from exc
        if category not in self.ALLOWED_CATEGORIES:
            raise LLMInvalidOutputError("资产辅助分类类别不在允许值内")
        if not 0 <= confidence <= 1:
            raise LLMInvalidOutputError("资产辅助分类置信度超出范围")
        if not reason or len(reason) > 120 or not isinstance(review, bool):
            raise LLMInvalidOutputError("资产辅助分类理由或复核标记无效")
        return category, confidence, reason, review


@dataclass
class PolicyRetrievalTool:
    knowledge_base: ControlledPolicyKnowledgeBase

    def retrieve_scope(self) -> list[PolicyEvidence]:
        return self.knowledge_base.retrieve(
            query="设备 器具 500万元 新购进 投入使用 次月 选择适用",
            limit=5,
        )

    def retrieve_for(self, assessment: AssetAssessment) -> list[PolicyEvidence]:
        if assessment.status == AssessmentStatus.NEEDS_INFORMATION:
            return []
        evidence = self.knowledge_base.retrieve(
            query="设备 器具 一次性税前扣除",
            reason_codes=assessment.reason_codes,
            limit=4,
        )
        if evidence:
            return evidence
        return self.knowledge_base.retrieve(query="设备器具 选择适用", limit=2)


class EvidenceVerificationTool:
    REQUIRED_FACT_FIELDS = (
        "asset_id", "fixed_asset_category", "building_flag", "unit_tax_basis",
        "acquisition_method", "placed_in_service_date", "evidence_status",
    )

    def verify(
        self,
        raw: dict[str, Any],
        assessment: AssetAssessment,
        policy_evidence: list[PolicyEvidence],
    ) -> EvidenceVerification:
        has_facts = all(raw.get(field) not in (None, "") for field in self.REQUIRED_FACT_FIELDS)
        has_reasons = bool(assessment.reason_codes)
        policy_required = assessment.status != AssessmentStatus.NEEDS_INFORMATION
        has_policy = bool(policy_evidence)
        calculation_required = assessment.status == AssessmentStatus.POTENTIALLY_APPLICABLE
        has_calculation = assessment.calculations is not None if calculation_required else True
        missing = []
        if not has_facts:
            missing.append("资产事实")
        if not has_reasons:
            missing.append("规则/原因代码")
        if policy_required and not has_policy:
            missing.append("政策来源")
        if not has_calculation:
            missing.append("计算依据")
        if assessment.status == AssessmentStatus.NEEDS_INFORMATION:
            missing.append("待补充资产事实")
        status = "完整" if not missing else ("部分" if has_reasons else "缺失")
        return EvidenceVerification(
            evidence_status=status,
            has_asset_facts=has_facts,
            has_reason_codes=has_reasons,
            has_policy_source=has_policy,
            has_calculation_basis=has_calculation,
            missing_items=tuple(missing),
        )


def build_condition_checks(
    raw: dict[str, Any], assessment: AssetAssessment
) -> list[ConditionCheck]:
    codes = set(assessment.reason_codes)
    pending = assessment.status == AssessmentStatus.NEEDS_INFORMATION

    def state(fail_code: str, review_codes: set[str] | None = None) -> tuple[str, str]:
        if fail_code in codes:
            return "未通过", fail_code
        review_hit = codes.intersection(review_codes or set())
        if pending or review_hit:
            review_code = next(
                (code for code in assessment.reason_codes if code in review_hit),
                assessment.reason_codes[0] if codes else "FACT_PENDING",
            )
            return "待确认", review_code
        return "通过", "CONDITION_PASSED"

    nature_state, nature_code = state(
        "BUILDING_EXCLUDED", {"ASSET_NATURE_UNCERTAIN", "ASSET_CLASSIFICATION_CONFLICT"}
    )
    threshold_state, threshold_code = state("UNIT_BASIS_OVER_THRESHOLD")
    period_state, period_code = state("ACQUISITION_OUTSIDE_POLICY_PERIOD")
    year_state, year_code = state("DEDUCTION_YEAR_MISMATCH")
    evidence_review = codes.intersection({"EVIDENCE_INCOMPLETE", "CLAIM_STATUS_REVIEW"})
    evidence_state = "待确认" if pending or evidence_review else "通过"
    evidence_code = next(
        (code for code in assessment.reason_codes if code in evidence_review),
        "CONDITION_PASSED",
    )
    return [
        ConditionCheck(
            "设备、器具范围",
            f"类别={_display(raw.get('fixed_asset_category'))}；building_flag={_display(raw.get('building_flag'))}",
            nature_state,
            nature_code,
        ),
        ConditionCheck(
            "单台（套）单位价值不超过500万元",
            _display(raw.get("unit_tax_basis")),
            threshold_state,
            threshold_code,
        ),
        ConditionCheck(
            "资产购进政策窗口",
            f"方式={_display(raw.get('acquisition_method'))}；规则购进日={_display(assessment.acquisition_date)}",
            period_state,
            period_code,
        ),
        ConditionCheck(
            "投入使用次月所属评估年度",
            f"投用日={_display(raw.get('placed_in_service_date'))}；扣除所属年度={_display(assessment.deduction_year)}",
            year_state,
            year_code,
        ),
        ConditionCheck(
            "享受状态与证据",
            f"已享受={_display(raw.get('policy_already_claimed'))}；evidence_status={_display(raw.get('evidence_status'))}",
            evidence_state,
            evidence_code,
        ),
    ]

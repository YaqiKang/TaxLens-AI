from __future__ import annotations

from pathlib import Path
from typing import Any

from taxlens_core.models import AssessmentParameters, AssessmentStatus
from taxlens_web.services import DataCheckResult

from .models import AgentBatchRun, AssetAgentResult, ToolTraceStep
from .providers import StructuredLLMProvider, provider_from_env, timeout_from_env
from .retrieval import ControlledPolicyKnowledgeBase
from .tools import (
    AssetClassificationTool,
    DeterministicRuleTool,
    EvidenceVerificationTool,
    LedgerParsingTool,
    PolicyRetrievalTool,
    TaxCalculationTool,
    build_condition_checks,
)


class TaxLensAgent:
    """Single task agent. It orchestrates tools but never replaces frozen decisions."""

    def __init__(
        self,
        *,
        knowledge_base: ControlledPolicyKnowledgeBase,
        provider: StructuredLLMProvider,
        timeout_seconds: float = 8.0,
    ):
        self.provider = provider
        self.ledger_tool = LedgerParsingTool()
        self.classification_tool = AssetClassificationTool(
            provider, timeout_seconds=timeout_seconds
        )
        self.policy_tool = PolicyRetrievalTool(knowledge_base)
        self.rule_tool = DeterministicRuleTool()
        self.calculation_tool = TaxCalculationTool()
        self.evidence_tool = EvidenceVerificationTool()

    def run(
        self,
        source_path: str | Path,
        parameters: AssessmentParameters,
        *,
        checked: DataCheckResult | None = None,
    ) -> AgentBatchRun:
        trace: list[ToolTraceStep] = []
        warnings: list[str] = []

        check = checked or self.ledger_tool.parse(source_path, parameters)
        trace.append(ToolTraceStep(
            "ledger_parsing", "台账解析", "success" if check.can_assess else "blocked",
            f"读取{check.total_rows}条记录；{check.processable_rows}条可处理。",
        ))
        if not check.can_assess:
            raise ValueError("Batch-blocking issues must be resolved before agent run")

        classifications: dict[int, Any] = {}
        called = 0
        degraded = 0
        for raw in check.records:
            result = self.classification_tool.classify(raw)
            classifications[int(raw["_row_number"])] = result
            if result.called:
                called += 1
            if result.provider_status.startswith("degraded_"):
                degraded += 1
        class_status = "degraded" if degraded else "success"
        class_summary = (
            f"{called}条触发语义辅助；{degraded}条因模型不可用安全转人工复核。"
            if called else "结构化字段未触发语义辅助。"
        )
        trace.append(ToolTraceStep("asset_classification", "资产性质辅助识别", class_status, class_summary))
        if degraded:
            warnings.append("部分资产语义辅助已降级；原始结构化字段和冻结规则结果未被修改。")

        scope_evidence = self.policy_tool.retrieve_scope()
        trace.append(ToolTraceStep(
            "policy_retrieval", "政策检索", "success" if scope_evidence else "no_match",
            f"受控官方知识库为当前单一场景定位{len(scope_evidence)}条核心政策证据。"
            if scope_evidence else "当前受控知识库未检索到场景政策，未生成替代依据。",
        ))

        assessment = self.rule_tool.evaluate(source_path, parameters)
        trace.append(ToolTraceStep(
            "deterministic_rule", "规则判断", "success",
            f"冻结Phase 1规则已处理{len(assessment.assessments)}条资产。",
        ))

        verified_calculations = self.calculation_tool.verify(assessment, check.records)
        trace.append(ToolTraceStep(
            "tax_calculation", "税务计算", "success",
            f"{len(verified_calculations)}条可选择适用资产通过确定性计算复核。",
        ))

        raw_by_row = {int(record["_row_number"]): record for record in check.records}
        evidence_by_row = {}
        for item in assessment.assessments:
            evidence = self.policy_tool.retrieve_for(item)
            evidence_by_row[item.row_number] = evidence

        assets: dict[str, AssetAgentResult] = {}
        complete_count = 0
        for item in assessment.assessments:
            raw = raw_by_row[item.row_number]
            evidence = evidence_by_row[item.row_number]
            verification = self.evidence_tool.verify(raw, item, evidence)
            if verification.evidence_status == "完整":
                complete_count += 1
            asset_id = item.asset_id or f"ROW-{item.row_number}"
            assets[asset_id] = AssetAgentResult(
                asset_id=asset_id,
                raw_facts=self._safe_facts(raw),
                classification=classifications[item.row_number],
                conditions=build_condition_checks(raw, item),
                policy_evidence=evidence,
                evidence_verification=verification,
                explanation=self._explain(item.status.value, item.reason_messages, verification.evidence_status),
            )
        trace.append(ToolTraceStep(
            "evidence_verification", "证据核验", "success",
            f"{complete_count}/{len(assessment.assessments)}条形成完整展示证据链；其余明确标记缺口。",
        ))
        return AgentBatchRun(
            assessment=assessment,
            asset_results=assets,
            tool_trace=trace,
            provider_status=getattr(self.provider, "status", "unknown"),
            warnings=warnings,
        )

    @staticmethod
    def _safe_facts(raw: dict[str, Any]) -> dict[str, Any]:
        return {
            key: (value.isoformat() if hasattr(value, "isoformat") else str(value) if value is not None else None)
            for key, value in raw.items() if key != "_row_number"
        }

    @staticmethod
    def _explain(status: str, messages: list[str], evidence_state: str) -> str:
        reason = "；".join(messages) if messages else "未形成扩展判断"
        return (
            f"当前辅助评估状态为“{status}”。依据冻结规则记录：{reason}。"
            f"展示证据链状态为“{evidence_state}”；本说明不构成税务申报意见。"
        )


def build_default_agent(root: str | Path) -> TaxLensAgent:
    root_path = Path(root)
    return TaxLensAgent(
        knowledge_base=ControlledPolicyKnowledgeBase(
            root_path / "knowledge/policies/policy_chunks.json"
        ),
        provider=provider_from_env(),
        timeout_seconds=timeout_from_env(),
    )

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from taxlens_core.models import WorkbookAssessment


@dataclass(frozen=True)
class ToolTraceStep:
    tool_name: str
    label: str
    status: str
    summary: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ClassificationSuggestion:
    called: bool
    provider_status: str
    suggested_category: str
    confidence: float
    reason: str
    requires_human_review: bool
    original_category: str | None
    original_building_flag: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PolicyEvidence:
    chunk_id: str
    policy_name: str
    document_number: str
    issuing_authority: str
    effective_or_applicable_period: str
    source_url: str
    clause_reference: str
    relevant_text: str
    knowledge_base_updated_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ConditionCheck:
    condition_name: str
    current_fact: str
    status: str
    reason_code: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EvidenceVerification:
    evidence_status: str
    has_asset_facts: bool
    has_reason_codes: bool
    has_policy_source: bool
    has_calculation_basis: bool
    missing_items: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["missing_items"] = list(self.missing_items)
        return value


@dataclass
class AssetAgentResult:
    asset_id: str
    raw_facts: dict[str, Any]
    classification: ClassificationSuggestion
    conditions: list[ConditionCheck]
    policy_evidence: list[PolicyEvidence]
    evidence_verification: EvidenceVerification
    explanation: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "raw_facts": self.raw_facts,
            "classification": self.classification.to_dict(),
            "conditions": [item.to_dict() for item in self.conditions],
            "policy_evidence": [item.to_dict() for item in self.policy_evidence],
            "evidence_verification": self.evidence_verification.to_dict(),
            "explanation": self.explanation,
        }


@dataclass
class AgentBatchRun:
    assessment: WorkbookAssessment
    asset_results: dict[str, AssetAgentResult]
    tool_trace: list[ToolTraceStep]
    provider_status: str
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "assessment": self.assessment.to_dict(),
            "asset_results": {key: value.to_dict() for key, value in self.asset_results.items()},
            "tool_trace": [item.to_dict() for item in self.tool_trace],
            "provider_status": self.provider_status,
            "warnings": self.warnings,
        }

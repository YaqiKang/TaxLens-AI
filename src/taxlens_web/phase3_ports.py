"""Compatibility protocols retained after Phase 3 Agent/evidence implementation."""

from __future__ import annotations

from typing import Protocol

from taxlens_core.models import AssetAssessment


class PolicyEvidenceProvider(Protocol):
    """Future policy evidence-chain provider interface."""

    def evidence_for(self, assessment: AssetAssessment) -> list[dict[str, str]]: ...


class AgentNarrativeProvider(Protocol):
    """Future TaxLens Agent narrative provider interface."""

    def explain(self, assessment: AssetAssessment) -> str: ...


# Phase 3 uses concrete implementations in ``taxlens_agent``. These small
# protocols remain available only as stable presentation-layer seams.

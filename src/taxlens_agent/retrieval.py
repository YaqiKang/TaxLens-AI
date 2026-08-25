from __future__ import annotations

import json
from pathlib import Path

from .models import PolicyEvidence


class ControlledPolicyKnowledgeBase:
    """Local, allow-listed retrieval only. It never performs network access."""

    def __init__(self, knowledge_file: str | Path):
        payload = json.loads(Path(knowledge_file).read_text(encoding="utf-8"))
        if not payload.get("governance", {}).get("official_sources_only"):
            raise ValueError("Policy knowledge base must be official-source-only")
        self.metadata = payload
        self._chunks = payload.get("chunks", [])

    @property
    def allowed_document_numbers(self) -> set[str]:
        return {item["document_number"] for item in self._chunks}

    @property
    def allowed_source_urls(self) -> set[str]:
        return {item["source_url"] for item in self._chunks}

    def retrieve(
        self,
        *,
        query: str = "",
        reason_codes: list[str] | None = None,
        limit: int = 4,
    ) -> list[PolicyEvidence]:
        reason_set = set(reason_codes or [])
        tokens = {token for token in query.replace("、", " ").replace("，", " ").split() if token}
        scored: list[tuple[int, str, dict]] = []
        for chunk in self._chunks:
            score = 10 * len(reason_set.intersection(chunk.get("reason_codes", [])))
            searchable = " ".join([
                chunk.get("policy_name", ""),
                chunk.get("document_number", ""),
                chunk.get("relevant_text", ""),
                " ".join(chunk.get("tags", [])),
            ])
            score += sum(1 for token in tokens if token in searchable)
            if score > 0:
                scored.append((score, chunk["chunk_id"], chunk))
        scored.sort(key=lambda value: (-value[0], value[1]))
        return [self._to_evidence(item) for _, _, item in scored[:limit]]

    @staticmethod
    def _to_evidence(item: dict) -> PolicyEvidence:
        return PolicyEvidence(**{
            key: item[key]
            for key in [
                "chunk_id", "policy_name", "document_number", "issuing_authority",
                "effective_or_applicable_period", "source_url", "clause_reference",
                "relevant_text", "knowledge_base_updated_at",
            ]
        })

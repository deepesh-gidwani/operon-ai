"""The three Operon AI agents.

DataAgent   — deterministic pandas only (allowlisted functions). Never invents
              data; per-analysis failures become warnings. The short data brief
              is the only LLM call, kept separate from the evidence.
InsightAgent — muse-spark-1.3 via the Meta Model API. Claims must cite metric
              ids from the evidence bundle; unknown references are dropped.
ActionAgent  — muse-spark-1.3 via the Meta Model API. Prioritized actions, each
              linked to evidence with expected impact and uncertainty.

Every model response is validated against a Pydantic schema. Validation
failures get one bounded correction retry, then fail honestly.
"""

from __future__ import annotations

import pandas as pd
from pydantic import ValidationError

from . import analytics
from .meta_client import MetaAPIError
from .models import (
    ActionItem,
    ActionListResponse,
    DataBriefResponse,
    DataProfile,
    EvidenceBundle,
    ExecutionPlan,
    Insight,
    InsightListResponse,
)


def _validated_chat(meta, messages: list[dict[str, str]], schema, max_tokens: int):
    """chat_json + Pydantic validation with one bounded correction retry."""
    result = meta.chat_json(messages, max_tokens=max_tokens)
    try:
        return schema.model_validate(result)
    except ValidationError as first_exc:
        retry_messages = [
            *messages,
            {
                "role": "user",
                "content": (
                    "Your previous reply did not match the required schema: "
                    f"{first_exc.errors()[:3]}. Reply again with exactly one JSON "
                    "object matching the schema and nothing else."
                ),
            },
        ]
        result = meta.chat_json(retry_messages, max_tokens=max_tokens)
        try:
            return schema.model_validate(result)
        except ValidationError as exc:
            raise MetaAPIError(f"Model response failed validation: {exc}") from exc


def _evidence_context(bundle: EvidenceBundle) -> str:
    if not bundle.metrics:
        return "(no metrics computed)"
    return "\n".join(f"- {m.id} | {m.label} | {m.detail}" for m in bundle.metrics)


class DataAgent:
    """Deterministic evidence collector. No model calls in the metrics path."""

    name = "data"

    def collect(self, df: pd.DataFrame, plan: ExecutionPlan) -> EvidenceBundle:
        return analytics.collect_evidence(df, plan.selected_analyses)

    def profile(self, df: pd.DataFrame) -> DataProfile:
        return analytics.profile_dataframe(df)

    def write_brief(self, objective: str, bundle: EvidenceBundle, meta) -> str:
        """LLM-written summary of what the data covers. Evidence stays untouched."""
        parsed = _validated_chat(
            meta,
            [
                {
                    "role": "system",
                    "content": (
                        "You are the Data agent of Operon AI, a business operations "
                        "intelligence platform. Reply with exactly one JSON object."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Business objective: {objective}\n\nDeterministic evidence:\n"
                        f"{_evidence_context(bundle)}\n\n"
                        'Return exactly: {"data_brief": "<3-5 sentence brief describing what the data '
                        "covers, its grain, and what can and cannot be answered from it>\"}."
                    ),
                },
            ],
            DataBriefResponse,
            max_tokens=1500,
        )
        return parsed.data_brief.strip()


class InsightAgent:
    """Finds trends and anomalies in the evidence. Every claim cites metrics."""

    name = "insight"

    def run(
        self,
        objective: str,
        data_brief: str,
        bundle: EvidenceBundle,
        profile: DataProfile,
        meta,
        max_insights: int = 5,
    ) -> tuple[list[Insight], list[str]]:
        warnings: list[str] = []
        parsed = _validated_chat(
            meta,
            [
                {
                    "role": "system",
                    "content": (
                        "You are the Insight agent of Operon AI. Every claim must be backed by "
                        "the provided metrics. Use only metric ids from the allowed list. "
                        "Reply with exactly one JSON object."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Business objective: {objective}\n\nData brief: {data_brief}\n\n"
                        f"Deterministic evidence (metric id | label | detail):\n"
                        f"{_evidence_context(bundle)}\n\n"
                        f"Allowed metric ids: {sorted(bundle.ids())}\n\n"
                        "Return exactly:\n"
                        '{"insights": [{"title": "<short>", "body": "<2-4 sentences, cite concrete '
                        'numbers from the evidence>", "evidence": ["<statistic 1>", "<statistic 2>"], '
                        '"metric_refs": ["<metric id>", "<metric id>"]}]}\n'
                        f"3 to {max_insights} insights. metric_refs must use only allowed ids."
                    ),
                },
            ],
            InsightListResponse,
            max_tokens=2500,
        )
        insights, dropped = self.filter_refs(parsed.insights, bundle)
        if dropped:
            warnings.append(f"Dropped {dropped} unknown metric reference(s) from insights.")
        if not insights:
            raise MetaAPIError("Insight agent returned no insights.")
        return insights, warnings

    @staticmethod
    def filter_refs(
        insights: list[Insight], bundle: EvidenceBundle
    ) -> tuple[list[Insight], int]:
        known = bundle.ids()
        dropped = 0
        for insight in insights:
            kept = [r for r in insight.metric_refs if r in known]
            dropped += len(insight.metric_refs) - len(kept)
            insight.metric_refs = kept
        return insights, dropped


class ActionAgent:
    """Turns insights into prioritized, evidence-linked recommendations."""

    name = "action"

    def run(
        self,
        objective: str,
        data_brief: str,
        insights: list[Insight],
        bundle: EvidenceBundle,
        meta,
        max_actions: int = 5,
    ) -> tuple[list[ActionItem], list[str]]:
        warnings: list[str] = []
        insight_text = "\n".join(
            f"- {i.title}: {i.body} (metrics: {i.metric_refs or 'none'})" for i in insights
        )
        parsed = _validated_chat(
            meta,
            [
                {
                    "role": "system",
                    "content": (
                        "You are the Action agent of Operon AI. Recommend concrete, prioritized "
                        "next steps grounded in the evidence. Reply with exactly one JSON object."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Business objective: {objective}\n\nData brief: {data_brief}\n\n"
                        f"Agreed insights:\n{insight_text}\n\n"
                        f"Deterministic evidence (metric id | label | detail):\n"
                        f"{_evidence_context(bundle)}\n\n"
                        f"Allowed metric ids: {sorted(bundle.ids())}\n\n"
                        "Return exactly:\n"
                        '{"actions": [{"title": "<short>", "body": "<what to do and why, 1-3 '
                        'sentences>", "expected_impact": "<one line>", "effort": '
                        '"low|medium|high", "evidence_refs": ["<metric id>"], '
                        '"uncertainty": "<one line on what is uncertain>"}]}\n'
                        f"3 to {max_actions} actions, highest priority first. "
                        "evidence_refs must use only allowed ids."
                    ),
                },
            ],
            ActionListResponse,
            max_tokens=2500,
        )
        actions = self._normalize(parsed.actions, bundle)
        dropped = self._filter_refs(actions, bundle)
        if dropped:
            warnings.append(f"Dropped {dropped} unknown metric reference(s) from actions.")
        if not actions:
            raise MetaAPIError("Action agent returned no actions.")
        return actions, warnings

    @staticmethod
    def _normalize(actions: list[ActionItem], bundle: EvidenceBundle) -> list[ActionItem]:
        del bundle
        normalized = []
        for rank, action in enumerate(actions[:5], start=1):
            effort = str(action.effort).strip().lower()
            if effort not in ("low", "medium", "high"):
                effort = "medium"
            action.rank = rank
            action.effort = effort  # type: ignore[assignment]
            normalized.append(action)
        return normalized

    @staticmethod
    def _filter_refs(actions: list[ActionItem], bundle: EvidenceBundle) -> int:
        known = bundle.ids()
        dropped = 0
        for action in actions:
            kept = [r for r in action.evidence_refs if r in known]
            dropped += len(action.evidence_refs) - len(kept)
            action.evidence_refs = kept
        return dropped

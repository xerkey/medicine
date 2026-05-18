"""Top-level Checker: retrieve references, build prompt, call Claude.

Default model is `claude-sonnet-4-6` — good intelligence-cost balance for
this classification task. Override via `Checker(model="claude-opus-4-7")`
for higher-stakes runs.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import anthropic

from .prompts import (
    JUDGMENT_SCHEMA,
    SYSTEM_PROMPT,
    build_category_reference,
    build_variable_block,
)
from .retrieve import ReferenceIndex


@dataclass
class CheckResult:
    verdict: str
    severity: str
    violated_articles: list[str]
    matched_ng_pattern_ids: list[str]
    rationale: str
    rewrite_suggestion: str
    usage: dict[str, int] = field(default_factory=dict)
    retrieval_meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "severity": self.severity,
            "violated_articles": self.violated_articles,
            "matched_ng_pattern_ids": self.matched_ng_pattern_ids,
            "rationale": self.rationale,
            "rewrite_suggestion": self.rewrite_suggestion,
            "usage": self.usage,
            "retrieval_meta": self.retrieval_meta,
        }


class Checker:
    def __init__(
        self,
        model: str = "claude-sonnet-4-6",
        *,
        index: ReferenceIndex | None = None,
        client: anthropic.Anthropic | None = None,
    ) -> None:
        self.model = model
        self.index = index or ReferenceIndex()
        self.client = client or anthropic.Anthropic()

    def check(
        self,
        text: str,
        *,
        category: str,
        medium: str = "Web",
        subtype: str = "",
    ) -> CheckResult:
        retrieval = self.index.retrieve(text, category)
        category_ref = build_category_reference(category, retrieval)
        variable = build_variable_block(text, medium, subtype, retrieval)

        # Cache breakpoints: system prompt (static) + category reference
        # (stable per category). The category block reuses its cache entry
        # across every call for the same category — only the trailing
        # variable block recomputes per request.
        response = self.client.messages.create(
            model=self.model,
            max_tokens=2048,
            system=[
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": category_ref,
                            "cache_control": {"type": "ephemeral"},
                        },
                        {"type": "text", "text": variable},
                    ],
                }
            ],
            output_config={
                "format": {"type": "json_schema", "schema": JUDGMENT_SCHEMA}
            },
        )

        text_block = next(b for b in response.content if b.type == "text")
        data = json.loads(text_block.text)

        return CheckResult(
            verdict=data["verdict"],
            severity=data["severity"],
            violated_articles=data["violated_articles"],
            matched_ng_pattern_ids=data["matched_ng_pattern_ids"],
            rationale=data["rationale"],
            rewrite_suggestion=data["rewrite_suggestion"],
            usage={
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
                "cache_creation_input_tokens": response.usage.cache_creation_input_tokens,
                "cache_read_input_tokens": response.usage.cache_read_input_tokens,
            },
            retrieval_meta={
                "ng_keyword_hits": len(retrieval.ng_pattern_hits),
                "category_rules_count": len(retrieval.category_rules),
                "ok_patterns_count": len(retrieval.ok_patterns),
                "related_cases_count": len(retrieval.related_cases),
            },
        )

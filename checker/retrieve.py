"""Rule-based retrieval over the reference dataset.

We deliberately avoid embedding-based RAG: the NG patterns are too short
(many are 2-6 character keywords), the discriminating signal is keyword
presence + category, and embeddings would confuse「シミを薄くする」(NG) with
「シミを防ぐ」(OK).

Strategy:
  1. Category rules + efficacy range: always included for the category (small)
  2. NG / OK pattern hits: keyword-inverted-index lookup, then category filter
  3. Case studies: category match, capped
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .normalize import strip_for_matching

REF_DIR = Path(__file__).resolve().parent.parent / "reference"


@dataclass
class Retrieval:
    category_rules: list[dict[str, Any]]
    efficacy_range: dict[str, Any] | None
    ng_pattern_hits: list[dict[str, Any]]
    ok_patterns: list[dict[str, Any]]
    related_cases: list[dict[str, Any]]


class ReferenceIndex:
    def __init__(self, ref_dir: Path = REF_DIR) -> None:
        self.ref_dir = ref_dir
        self.ng_patterns = self._load_jsonl("ng_expression_patterns.jsonl")
        self.ok_patterns = self._load_jsonl("ok_expression_patterns.jsonl")
        self.case_studies = self._load_jsonl("case_studies.jsonl")
        self.category_rules = self._load_jsonl("category_rules.jsonl")
        self.cosmetic_56 = json.loads(
            (ref_dir / "cosmetic_efficacy_56.json").read_text(encoding="utf-8")
        )
        self.quasi_drug = json.loads(
            (ref_dir / "quasi_drug_efficacy.json").read_text(encoding="utf-8")
        )

        # Inverted index: normalized keyword -> [pattern_id]
        self.keyword_index: dict[str, list[str]] = {}
        for p in self.ng_patterns:
            for kw in p.get("ng_keywords", []) or []:
                if not kw:
                    continue
                norm = strip_for_matching(kw)
                if norm:
                    self.keyword_index.setdefault(norm, []).append(p["id"])

        self.id_to_ng = {p["id"]: p for p in self.ng_patterns}

    def _load_jsonl(self, name: str) -> list[dict[str, Any]]:
        path = self.ref_dir / name
        return [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    @staticmethod
    def _category_matches(rule_category: str, target_category: str) -> bool:
        if not rule_category:
            return False
        if rule_category == target_category or rule_category == "全般":
            return True
        # Substring matches: "化粧品/化粧品工業会" should match "化粧品",
        # "雑貨/EMS" should match "雑貨" or "医療機器" callers, etc.
        return target_category in rule_category or rule_category in target_category

    def retrieve(
        self,
        text: str,
        category: str,
        *,
        max_ng_hits: int = 20,
        max_ok_patterns: int = 12,
        max_cases: int = 5,
    ) -> Retrieval:
        cat_match = lambda c: self._category_matches(c, category)

        rules = [r for r in self.category_rules if cat_match(r.get("category", ""))]

        efficacy: dict[str, Any] | None = None
        if "化粧品" in category and "医薬部外品" not in category:
            efficacy = self.cosmetic_56
        elif "医薬部外品" in category:
            efficacy = self.quasi_drug

        stripped = strip_for_matching(text)
        ng_hit_ids: set[str] = set()
        for kw, ids in self.keyword_index.items():
            if kw in stripped:
                ng_hit_ids.update(ids)

        ng_hits = [
            self.id_to_ng[i]
            for i in ng_hit_ids
            if cat_match(self.id_to_ng[i].get("category", ""))
        ]
        # Order by severity (critical > high > medium > low) so the most
        # alarming hits show up first in the prompt.
        sev_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        ng_hits.sort(key=lambda p: sev_order.get(p.get("severity", "low"), 9))
        ng_hits = ng_hits[:max_ng_hits]

        ok_for_category = [
            p for p in self.ok_patterns if cat_match(p.get("category", ""))
        ][:max_ok_patterns]

        related_cases = [
            c for c in self.case_studies if cat_match(c.get("industry", ""))
        ][:max_cases]

        return Retrieval(
            category_rules=rules,
            efficacy_range=efficacy,
            ng_pattern_hits=ng_hits,
            ok_patterns=ok_for_category,
            related_cases=related_cases,
        )

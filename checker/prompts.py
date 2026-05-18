"""Prompt assembly for the judgment LLM call.

Layout (front-to-back, prefix-cache aware):
  [system prompt]                              ← cached (static)
  [category reference: rules + efficacy]       ← cached (stable per category)
  [variable: NG hits + OK examples + cases]    ← not cached
  [input text]                                 ← not cached
"""

from __future__ import annotations

import json
from typing import Any

from .retrieve import Retrieval


SYSTEM_PROMPT = """あなたは日本の薬機法（医薬品、医療機器等の品質、有効性及び安全性の確保等に関する法律）および関連法令（健康増進法、景品表示法、医療広告ガイドライン、ステマ規制等）に精通した広告コンプライアンスチェッカーです。

入力された広告表現を、与えられたメタデータ（カテゴリ、媒体）と参照データに基づいて判定してください。

判定区分:
- OK: 法令・ガイドラインに照らして問題なし
- GRAY: 条件次第で違反となる可能性がある、文脈依存、または専門家確認推奨
- NG: 明確な違反

判定方針:
1. メタデータで指定された「カテゴリ」を前提として判断する（化粧品か医薬部外品かで判定が変わる）
2. 提供された「該当カテゴリのルール」と「効能効果範囲」を最優先で参照する
3. 「キーワードヒットしたNGパターン候補」は要注意候補だが、機械的に該当判定せず文脈で判断する
4. 「認められる表現の参考」も照合し、適正範囲なら OK と判定する
5. 参照データにない表現でも、薬機法・関連法令の趣旨から判断する
6. 装飾文字・伏字・スペース挿入などの迂回手法は、実質的意味で判定する

severity の基準:
- critical: 刑事処分・課徴金レベルの重大違反（疾病治療訴求、未承認医薬品広告等）
- high: 措置命令・行政指導レベル
- medium: 適正広告基準違反、表現修正レベル
- low: 軽微・要注意

JSON 形式のみで出力し、説明文や前置きを付けないでください。"""


JUDGMENT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["OK", "GRAY", "NG"]},
        "severity": {
            "type": "string",
            "enum": ["low", "medium", "high", "critical"],
        },
        "violated_articles": {
            "type": "array",
            "items": {"type": "string"},
            "description": "違反する法令・基準（例: 薬機法第66条, 適正広告基準3-(4)）。OK の場合は空配列。",
        },
        "matched_ng_pattern_ids": {
            "type": "array",
            "items": {"type": "string"},
            "description": "判定根拠となった参照データの NG パターン ID（NG-XXX）。なければ空配列。",
        },
        "rationale": {
            "type": "string",
            "description": "判定理由（参照した条文・ルールを含めて簡潔に）。",
        },
        "rewrite_suggestion": {
            "type": "string",
            "description": "NG/GRAY の場合の言い換え提案。OK の場合は空文字列。",
        },
    },
    "required": [
        "verdict",
        "severity",
        "violated_articles",
        "matched_ng_pattern_ids",
        "rationale",
        "rewrite_suggestion",
    ],
    "additionalProperties": False,
}


def build_category_reference(category: str, retrieval: Retrieval) -> str:
    """The stable, per-category block — cache this."""
    parts: list[str] = [f"# 該当カテゴリ: {category}", "", "## カテゴリ別ルール"]
    if retrieval.category_rules:
        for r in retrieval.category_rules:
            line = f"- [{r.get('rule_type', '')}] {r.get('rule', '')}"
            exc = r.get("exception", "")
            if exc and exc not in ("ない", ""):
                line += f"（例外: {exc}）"
            parts.append(line)
    else:
        parts.append("（このカテゴリ用のルールデータなし — 一般原則で判断）")

    if retrieval.efficacy_range:
        parts.append("")
        parts.append("## 承認/許容される効能効果範囲")
        parts.append(
            json.dumps(retrieval.efficacy_range, ensure_ascii=False, indent=2)
        )
    return "\n".join(parts)


def build_variable_block(
    text: str,
    medium: str,
    subtype: str,
    retrieval: Retrieval,
) -> str:
    """Per-input block — varies every call, never cached."""
    parts: list[str] = [
        "# 入力メタデータ",
        f"- 媒体: {medium}",
    ]
    if subtype:
        parts.append(f"- サブタイプ: {subtype}")

    if retrieval.ng_pattern_hits:
        parts += ["", "# キーワードヒットしたNGパターン候補（要注意）"]
        for p in retrieval.ng_pattern_hits:
            parts.append(
                f"- [{p['id']}|{p.get('pattern_type', '')}|severity={p.get('severity', '')}] "
                f"例: 「{p.get('expression', '')}」 / 違反: {p.get('violation', '')} "
                f"/ 根拠: {p.get('violated_law', '')}"
            )
    else:
        parts += ["", "# キーワードヒット: なし（NG パターン辞書に直接の手がかりなし）"]

    if retrieval.ok_patterns:
        parts += ["", "# 該当カテゴリで認められる表現の例（OKの参考）"]
        for p in retrieval.ok_patterns:
            parts.append(
                f"- 「{p.get('expression', '')}」 — {p.get('rationale', '')}"
            )

    if retrieval.related_cases:
        parts += ["", "# 関連する過去事例"]
        for c in retrieval.related_cases:
            parts.append(
                f"- {c.get('year', '?')} {c.get('case_type', '')}: "
                f"{c.get('summary', '')}（{c.get('outcome', '')}）"
            )

    parts += [
        "",
        "# 判定対象の広告表現",
        f"「{text}」",
        "",
        "上記の参照情報に基づいて判定し、指定されたJSONスキーマで出力してください。",
    ]
    return "\n".join(parts)

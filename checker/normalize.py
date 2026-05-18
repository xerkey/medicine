"""Text normalization for adversarial input handling.

The keyword lookup against `ng_keywords` would miss obvious bypasses like
「シ★ミ」「シ ミ」「シ・ミ」 without normalization. We produce two views:
- `normalize_text`: NFKC + strip zero-width chars (safe, lossless)
- `strip_for_matching`: above + strip filler chars used for evasion
  (spaces, middots, asterisks, stars, etc.)

The LLM still sees the original text — these helpers are only used to
decide which reference patterns to retrieve.
"""

from __future__ import annotations

import re
import unicodedata

_FILLER_CHARS = re.compile(
    r"[★☆●○■□◆◇♥♡⭐♪♫*＊✦✧·・　\s\.\-_'\"`/\\|()（）\[\]【】]"
)
_ZERO_WIDTH = re.compile(r"[​-‍﻿]")


def normalize_text(text: str) -> str:
    """Lossless normalization: NFKC + strip zero-width."""
    text = unicodedata.normalize("NFKC", text)
    return _ZERO_WIDTH.sub("", text)


def strip_for_matching(text: str) -> str:
    """Aggressive normalization for keyword lookup against evasion attempts."""
    return _FILLER_CHARS.sub("", normalize_text(text))

"""Run a Checker against an evaluation dataset.

Usage:
    python scripts/evaluate.py --eval-file evaluation/eval_dataset.jsonl --limit 10
    python scripts/evaluate.py --eval-file evaluation/boundary_cases.jsonl
    python scripts/evaluate.py --eval-file evaluation/adversarial_cases.jsonl --model claude-opus-4-7
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from checker import Checker


def load_cases(eval_file: Path) -> list[dict]:
    with eval_file.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def evaluate(
    checker: Checker,
    cases: list[dict],
    *,
    output_path: Path | None,
) -> dict:
    results: list[dict] = []
    correct = 0
    by_type: Counter[str] = Counter()
    by_type_correct: Counter[str] = Counter()
    by_verdict: Counter[tuple[str, str]] = Counter()  # (expected, actual) → count
    total_cache_read = 0
    total_input = 0
    total_output = 0

    start = time.time()
    for i, case in enumerate(cases, 1):
        case_id = case.get("id", f"case-{i}")
        expected = case.get("verdict", "?")
        case_type = case.get("type", "unknown")
        category = case.get("category", "全般")
        text = case.get("input", "")

        try:
            result = checker.check(text, category=category)
            actual = result.verdict
            is_correct = actual == expected
            correct += int(is_correct)
            by_type[case_type] += 1
            if is_correct:
                by_type_correct[case_type] += 1
            by_verdict[(expected, actual)] += 1
            total_cache_read += result.usage.get("cache_read_input_tokens", 0)
            total_input += result.usage.get("input_tokens", 0)
            total_output += result.usage.get("output_tokens", 0)

            marker = "✓" if is_correct else "✗"
            print(
                f"[{i:3d}/{len(cases)}] {case_id} ({case_type:12s}) "
                f"expected={expected:4s} actual={actual:4s} {marker}  "
                f"input[:60]={text[:60]!r}"
            )

            results.append(
                {
                    "id": case_id,
                    "type": case_type,
                    "category": category,
                    "input": text,
                    "expected_verdict": expected,
                    "actual_verdict": actual,
                    "correct": is_correct,
                    "actual_severity": result.severity,
                    "actual_rationale": result.rationale,
                    "actual_rewrite": result.rewrite_suggestion,
                    "matched_ng_ids": result.matched_ng_pattern_ids,
                    "retrieval_meta": result.retrieval_meta,
                }
            )
        except Exception as e:  # noqa: BLE001
            print(f"[{i:3d}/{len(cases)}] {case_id} ERROR: {e}")
            results.append({"id": case_id, "error": str(e)})

    elapsed = time.time() - start

    print("\n=== Summary ===")
    print(f"Overall: {correct}/{len(cases)} = {correct / len(cases) * 100:.1f}%")
    for t in sorted(by_type):
        n = by_type[t]
        ok = by_type_correct[t]
        print(f"  {t:14s} {ok:3d}/{n:3d} = {ok / n * 100:5.1f}%")
    print("\nConfusion matrix (expected × actual):")
    verdicts = ["OK", "GRAY", "NG"]
    print("        " + "  ".join(f"{v:>5s}" for v in verdicts))
    for exp in verdicts:
        row = "  ".join(f"{by_verdict[(exp, act)]:5d}" for act in verdicts)
        print(f"  {exp:5s}  {row}")
    print(f"\nElapsed: {elapsed:.1f}s ({elapsed / len(cases):.2f}s/case)")
    print(
        f"Tokens: input={total_input:,} output={total_output:,} "
        f"cache_read={total_cache_read:,}"
    )

    if output_path:
        with output_path.open("w", encoding="utf-8") as f:
            for r in results:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"\nDetailed results -> {output_path}")

    return {
        "total": len(cases),
        "correct": correct,
        "accuracy": correct / len(cases) if cases else 0.0,
        "by_type": dict(by_type),
        "by_type_correct": dict(by_type_correct),
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--eval-file",
        type=Path,
        default=Path("evaluation/eval_dataset.jsonl"),
    )
    p.add_argument("--model", default="claude-sonnet-4-6")
    p.add_argument("--limit", type=int, default=None, help="Cap number of cases")
    p.add_argument(
        "--output",
        type=Path,
        default=Path("evaluation/results.jsonl"),
        help="Per-case output (use '' to skip)",
    )
    args = p.parse_args()

    cases = load_cases(args.eval_file)
    if args.limit:
        cases = cases[: args.limit]
    print(f"Loaded {len(cases)} cases from {args.eval_file} (model={args.model})")

    checker = Checker(model=args.model)
    evaluate(
        checker,
        cases,
        output_path=args.output if str(args.output) else None,
    )


if __name__ == "__main__":
    main()

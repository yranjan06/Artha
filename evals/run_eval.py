#!/usr/bin/env python3
"""
Intent classifier eval runner.
Usage: python evals/run_eval.py
Exits with code 1 if accuracy < 100%.
"""

import json
import sys
import os
from pathlib import Path

# allow running from repo root or evals/
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from intent import classify

EVAL_PATH = Path(__file__).parent / "intent_eval.json"


def run():
    cases = json.loads(EVAL_PATH.read_text(encoding="utf-8"))

    passed = 0
    failed = 0
    errors = []

    print(f"Running {len(cases)} eval cases...\n")

    for case in cases:
        inp = case["input"]
        expected = case["expected"]
        try:
            got = classify(inp)
            ok = got == expected
        except Exception as e:
            got = f"ERROR: {e}"
            ok = False

        status = "✓" if ok else "✗"
        print(f"  {status}  [{expected:>7}] {inp!r}")
        if ok:
            passed += 1
        else:
            failed += 1
            errors.append({"input": inp, "expected": expected, "got": got})

    total = passed + failed
    accuracy = passed / total * 100 if total else 0

    print(f"\n{'='*50}")
    print(f"Results: {passed}/{total} passed — {accuracy:.1f}% accuracy")

    if errors:
        print("\nFailed cases:")
        for e in errors:
            print(f"  input={e['input']!r}  expected={e['expected']}  got={e['got']}")

    print()

    if failed > 0:
        print("❌ Eval failed — fix classifier before shipping.")
        sys.exit(1)
    else:
        print("✅ All eval cases passed.")
        sys.exit(0)


if __name__ == "__main__":
    run()

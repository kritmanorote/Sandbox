"""Calibrate the LLM judges against human labels.

An LLM judge is a classifier; its score is only trustworthy if it agrees with
human ground truth. This validates BOTH judges the gate relies on, each against
its own hand-labeled fixture (the agent is NOT involved — answers are fixed, so
the judge is measured in isolation):

  correctness judge  vs  judge_calibration.jsonl       (question+reference+answer)
  groundedness judge vs  groundedness_calibration.jsonl (context+answer)

For each it reports:
  - confusion matrix: WHERE it errs. FP (judge passes an answer a human rejects)
                      is the dangerous cell — bad answers slipping through.
  - accuracy        : % the judge matches the human.
  - Cohen's kappa   : agreement corrected for chance (>0.8 strong, 0.6-0.8
                      substantial, <0.6 weak).

Only once BOTH pass should run_eval.py's judge metrics be believed.

Run:  backend/.venv/Scripts/python.exe evals/calibrate_judge.py
"""
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from judges import judge_correctness, judge_groundedness

ACCURACY_BAR = 0.80
KAPPA_BAR = 0.60


def _load(filename: str) -> list[dict]:
    text = Path(__file__).with_name(filename).read_text()
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def calibrate(name: str, rows: list[dict], predict) -> bool:
    """Run `predict(row) -> (verdict, reason)` over labeled rows, compare to
    human_label, report confusion matrix / accuracy / kappa, return pass/fail."""
    print(f"\n===== {name}: {len(rows)} human-labeled examples =====")
    tp = tn = fp = fn = 0
    for r in rows:
        human = bool(r["human_label"])
        verdict, _ = predict(r)
        if verdict and human:           tp += 1; cell = "TP"
        elif not verdict and not human: tn += 1; cell = "TN"
        elif verdict and not human:     fp += 1; cell = "FP"   # too lenient (DANGER)
        else:                           fn += 1; cell = "FN"   # too strict
        print(f"  {'ok ' if verdict == human else 'XX '}[{cell}] "
              f"human={human!s:5} judge={verdict!s:5}  {r['note']}")

    n = len(rows)
    accuracy = (tp + tn) / n
    po = accuracy
    p_judge_t = (tp + fp) / n
    p_human_t = (tp + fn) / n
    pe = p_judge_t * p_human_t + (1 - p_judge_t) * (1 - p_human_t)
    kappa = (po - pe) / (1 - pe) if (1 - pe) else 1.0

    print(f"  confusion: TP={tp} FP={fp} FN={fn} TN={tn}   (FP = bad answers passed)")
    print(f"  accuracy {accuracy:.2f} (>= {ACCURACY_BAR})   kappa {kappa:.2f} (>= {KAPPA_BAR})")
    ok = accuracy >= ACCURACY_BAR and kappa >= KAPPA_BAR
    if fp:
        print(f"  WARNING: {fp} false positive(s) — judge passed answers a human rejected.")
    print(f"  -> {'TRUSTWORTHY' if ok else 'NOT CALIBRATED'}")
    return ok


def main():
    correctness_ok = calibrate(
        "correctness judge", _load("judge_calibration.jsonl"),
        lambda r: judge_correctness(r["question"], r["answer"], r["reference"]),
    )
    groundedness_ok = calibrate(
        "groundedness judge", _load("groundedness_calibration.jsonl"),
        lambda r: judge_groundedness(r["answer"], r["context"]),
    )

    print("\n" + "=" * 52)
    if correctness_ok and groundedness_ok:
        print("ALL JUDGES TRUSTWORTHY — gate metrics can be believed")
        sys.exit(0)
    print("SOME JUDGE NOT CALIBRATED — fix before trusting the gate")
    sys.exit(1)


if __name__ == "__main__":
    main()

"""Calibrate the LLM judge against human labels.

An LLM judge is a classifier; its score is only trustworthy if it agrees with
human ground truth. This runs the SAME judge the gate uses (judges.judge_verdict)
over hand-labeled (question, answer, human_label) triples and reports:

  - accuracy        : % the judge matches the human
  - confusion matrix: WHERE it errs. The dangerous cell is FP (judge passes an
                      answer a human would reject) — that's bad answers slipping
                      through your quality gate.
  - Cohen's kappa   : agreement corrected for chance (>0.8 strong, 0.6-0.8
                      substantial, <0.6 weak — don't trust the judge metric).

Only once this passes should judge_correct/mean in run_eval.py be believed.

Run:  backend/.venv/Scripts/python.exe evals/calibrate_judge.py
"""
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from judges import judge_correctness

ACCURACY_BAR = 0.80
KAPPA_BAR = 0.60


def main():
    rows = [json.loads(line) for line in
            Path(__file__).with_name("judge_calibration.jsonl").read_text().splitlines()
            if line.strip()]
    print(f"Calibrating judge against {len(rows)} human-labeled examples...\n")

    tp = tn = fp = fn = 0
    for r in rows:
        human = bool(r["human_label"])
        verdict, reason = judge_correctness(r["question"], r["answer"], r["reference"])
        if verdict and human:       tp += 1; cell = "TP"
        elif not verdict and not human: tn += 1; cell = "TN"
        elif verdict and not human: fp += 1; cell = "FP"   # judge too lenient (DANGER)
        else:                       fn += 1; cell = "FN"   # judge too strict
        mark = "ok " if verdict == human else "XX "
        print(f"  {mark}[{cell}] human={human!s:5} judge={verdict!s:5}  {r['note']}")

    n = len(rows)
    accuracy = (tp + tn) / n
    # Cohen's kappa: (observed - chance) / (1 - chance)
    po = accuracy
    p_judge_t = (tp + fp) / n
    p_human_t = (tp + fn) / n
    pe = p_judge_t * p_human_t + (1 - p_judge_t) * (1 - p_human_t)
    kappa = (po - pe) / (1 - pe) if (1 - pe) else 1.0

    print("\n=== Confusion matrix ===")
    print(f"             human PASS   human FAIL")
    print(f"  judge PASS    TP={tp:<3}      FP={fp:<3}  <- FP = bad answers slipping through")
    print(f"  judge FAIL    FN={fn:<3}      TN={tn:<3}")

    print("\n=== Calibration ===")
    print(f"  accuracy      {accuracy:.2f}  (>= {ACCURACY_BAR})")
    print(f"  Cohen's kappa {kappa:.2f}  (>= {KAPPA_BAR})")
    if fp:
        print(f"  WARNING: {fp} false positive(s) — the judge passed answers a human rejected.")

    trustworthy = accuracy >= ACCURACY_BAR and kappa >= KAPPA_BAR
    print(f"\n{'JUDGE TRUSTWORTHY — gate metric can be believed' if trustworthy else 'JUDGE NOT CALIBRATED — do not trust judge_correct/mean until fixed'}")
    sys.exit(0 if trustworthy else 1)


if __name__ == "__main__":
    main()

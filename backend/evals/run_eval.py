"""Eval gate: score the LIVE app against a golden dataset, pass/fail on thresholds.

This is the regression-gate shape (vs. eval_traces.py, which scores past traces):
  - data    : golden examples in dataset.jsonl (inputs + expectations)
  - predict_fn : calls the running backend /chat-langchain for each example
  - scorers : content correctness, search BEHAVIOR (trace-aware), LLM judge
  - gate    : aggregate each scorer; exit non-zero if any falls below threshold
              -> drop this into CI and a bad prompt change fails the build.

Prereqs: backend (:8000), gateway (:4000), MLflow (:5000) all running.
Run:  backend/.venv/Scripts/python.exe evals/run_eval.py
"""
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

import requests
import mlflow
from mlflow.entities import Feedback
from mlflow.genai.scorers import scorer

# aliased so the scorer functions below can take the descriptive metric names
from judges import judge_correctness as judge_correctness_fn
from judges import judge_groundedness as judge_groundedness_fn

mlflow.set_tracking_uri(os.environ.get("MLFLOW_TRACKING_URI", "http://localhost:5000"))
mlflow.set_experiment("sandbox-chat-evals")

BACKEND = os.environ.get("EVAL_BACKEND_URL", "http://localhost:8000")

# Pass thresholds — the gate. Tune per criticality.
THRESHOLDS = {
    "answer_contains/mean": 0.80,
    "correct_search_behavior/mean": 0.80,
    "judge_correctness/mean": 0.80,
    "judge_grounded/mean": 0.80,
}


def _retrieved_context(outputs) -> str:
    """Flatten the chunks the agent retrieved (tool_calls[].results) into one
    string — this is the RAG context the groundedness judge checks against."""
    chunks = []
    for tc in outputs.get("tool_calls", []):
        chunks.extend(tc.get("results", []))
    return "\n".join(chunks)


def predict_fn(question: str) -> dict:
    """Call the live app exactly as the frontend would. Returns reply + the
    tool_calls the agent made, so scorers can check both content and behavior."""
    r = requests.post(
        f"{BACKEND}/chat-langchain",
        json={"messages": [{"role": "user", "content": question}], "use_agent": True,
              "session_id": "eval-gate"},
        timeout=120,
    )
    r.raise_for_status()
    d = r.json()
    return {"reply": d.get("reply", ""), "tool_calls": d.get("tool_calls", [])}


@scorer
def answer_contains(outputs, expectations) -> bool:
    """Content check: does the reply contain every required keyword?"""
    text = (outputs.get("reply") or "").lower()
    return all(kw.lower() in text for kw in expectations["must_mention"])


@scorer
def correct_search_behavior(outputs, expectations) -> bool:
    """Behavior check: did the agent search the KB exactly when it should have?
    Catches both 'failed to ground an on-topic answer' and 'over-eagerly
    searched for an off-topic question' — neither visible from content alone."""
    used_search = len(outputs.get("tool_calls", [])) > 0
    return used_search == expectations["must_use_search"]


@scorer
def judge_correctness(inputs, outputs, expectations) -> Feedback:
    """Reference-based: grade the reply against the dataset's ground-truth
    reference, so the judge verifies facts instead of guessing from memory."""
    verdict, reason = judge_correctness_fn(
        inputs["question"], outputs.get("reply", ""), expectations["reference"])
    return Feedback(value=verdict, rationale=reason)


@scorer
def judge_grounded(outputs, expectations) -> Feedback:
    """RAG faithfulness: is the reply supported by the retrieved context?
    N/A when no search was expected (parametric answer, no context to ground in)."""
    if not expectations["must_use_search"]:
        return Feedback(value=True, rationale="N/A: no retrieval expected (parametric answer)")
    context = _retrieved_context(outputs)
    if not context:
        return Feedback(value=False, rationale="expected retrieval but agent retrieved nothing")
    verdict, reason = judge_groundedness_fn(outputs.get("reply", ""), context)
    return Feedback(value=verdict, rationale=reason)


def main():
    data = [json.loads(line) for line in
            Path(__file__).with_name("dataset.jsonl").read_text().splitlines() if line.strip()]
    print(f"Evaluating {len(data)} golden examples against {BACKEND} ...\n")

    results = mlflow.genai.evaluate(
        data=data,
        predict_fn=predict_fn,
        scorers=[answer_contains, correct_search_behavior, judge_correctness, judge_grounded],
    )

    print("\n=== Gate ===")
    failed = []
    for metric, threshold in THRESHOLDS.items():
        score = results.metrics.get(metric)
        ok = score is not None and score >= threshold
        print(f"  {'PASS' if ok else 'FAIL'}  {metric:32} {score}  (>= {threshold})")
        if not ok:
            failed.append(metric)

    print(f"\nEval run: {results.run_id}")
    if failed:
        print(f"\nGATE FAILED: {', '.join(failed)}")
        sys.exit(1)
    print("\nGATE PASSED")


if __name__ == "__main__":
    main()

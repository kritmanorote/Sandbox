"""Score existing traces with mlflow.genai.evaluate().

Three scorers, one per archetype:
  1. mentions_four_colors — pure code check on the output text
  2. used_search_tool     — code check on the TRACE (did a TOOL span run?)
  3. judge_correct        — LLM-as-judge: Gemini grades the answer

Run:  .venv/Scripts/python.exe eval_traces.py
"""
import json
import os

from dotenv import load_dotenv

load_dotenv()

import mlflow
import google.generativeai as genai
from mlflow.entities import Feedback
from mlflow.genai.scorers import scorer

mlflow.set_tracking_uri(os.environ.get("MLFLOW_TRACKING_URI", "http://localhost:5000"))
mlflow.set_experiment("sandbox-chat")
genai.configure(api_key=os.environ["GEMINI_API_KEY"])


@scorer
def mentions_four_colors(outputs) -> bool:
    """Deterministic string check: does the reply name all four ghost colors?"""
    text = str(outputs).lower()
    return all(c in text for c in ["red", "pink", "cyan", "orange"])


@scorer
def used_search_tool(trace) -> bool:
    """Trace-aware check: did the agent actually call a tool, or answer from
    parametric memory? Inspects span types inside the trace."""
    return any(s.span_type == "TOOL" for s in trace.data.spans)


@scorer
def judge_correct(inputs, outputs) -> Feedback:
    """LLM-as-judge: ask Gemini to grade the answer. Returns a Feedback with
    a verdict and a rationale, which MLflow attaches to the trace."""
    judge = genai.GenerativeModel("gemini-3.1-flash-lite")
    prompt = (
        "You are an evaluation judge. Grade the assistant answer below.\n\n"
        f"User input: {inputs}\n\nAssistant answer: {outputs}\n\n"
        "Is the answer factually correct and responsive to the input? "
        'Reply with ONLY a JSON object: {"verdict": "yes" or "no", "reason": "<one sentence>"}'
    )
    resp = judge.generate_content(prompt)
    text = resp.text
    try:
        payload = text[text.index("{"): text.rindex("}") + 1]
        d = json.loads(payload)
        return Feedback(value=d["verdict"], rationale=d.get("reason", ""))
    except Exception:
        return Feedback(value="unparseable", rationale=text[:200])


if __name__ == "__main__":
    traces = mlflow.search_traces(max_results=4, order_by=["timestamp_ms DESC"])
    print(f"Evaluating {len(traces)} traces...")
    results = mlflow.genai.evaluate(
        data=traces,
        scorers=[mentions_four_colors, used_search_tool, judge_correct],
    )
    print("\nEval run id:", results.run_id)
    print("\nAggregate metrics:")
    for k, v in sorted(results.metrics.items()):
        print(f"  {k}: {v}")

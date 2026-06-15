"""The LLM judge — single source of truth, used by BOTH the eval gate
(run_eval.py) and the calibration check (calibrate_judge.py).

Sharing one function is not just DRY: calibration is only valid if it measures
the exact judge the gate relies on. If the gate and the calibration used
different prompts/models, the agreement number would be meaningless.
"""
import json
import os

import google.generativeai as genai

_configured = False


def _ensure_configured() -> None:
    global _configured
    if not _configured:
        genai.configure(api_key=os.environ["GEMINI_API_KEY"])
        _configured = True


def judge_verdict(question: str, answer: str) -> tuple[bool, str]:
    """Grade an answer for factual correctness + responsiveness.
    Returns (verdict, reason). verdict True = acceptable."""
    _ensure_configured()
    model = genai.GenerativeModel("gemini-3.1-flash-lite")
    prompt = (
        "You are an evaluation judge. Grade the assistant answer.\n\n"
        f"Question: {question}\n\nAnswer: {answer}\n\n"
        "Is it factually correct AND responsive to the question? "
        "A correct answer may be terse. An incomplete or off-topic answer is NOT acceptable. "
        'Reply ONLY JSON: {"verdict": true or false, "reason": "<one sentence>"}'
    )
    text = model.generate_content(prompt).text
    try:
        d = json.loads(text[text.index("{"): text.rindex("}") + 1])
        return bool(d["verdict"]), d.get("reason", "")
    except Exception:
        return False, f"unparseable judge output: {text[:150]}"

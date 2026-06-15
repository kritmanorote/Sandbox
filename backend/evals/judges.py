"""The LLM judges — single source of truth, used by BOTH the eval gate
(run_eval.py) and the calibration check (calibrate_judge.py).

Two grounded judges, because a reference-FREE judge (question+answer only)
can't verify project-specific RAG facts — it falls back on parametric
knowledge or plausibility and will pass hallucinations that happen to sound
right. So each judge is given a source of truth:

  judge_correctness(question, answer, reference)
      "is the answer correct?" — graded against the REFERENCE ground truth,
      not the judge's own memory.

  judge_groundedness(answer, context)
      "did the answer make this up?" — every claim must be supported by the
      retrieved CONTEXT (RAG faithfulness). Catches hallucination even when
      the answer is coincidentally correct.

A RAG app needs both: correctness catches wrong answers (bad retrieval);
groundedness catches right-sounding answers the model invented (ignored
retrieval). Neither is possible without giving the judge the relevant truth.
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


def _ask(prompt: str) -> tuple[bool, str]:
    _ensure_configured()
    model = genai.GenerativeModel("gemini-3.1-flash-lite")
    text = model.generate_content(prompt).text
    try:
        d = json.loads(text[text.index("{"): text.rindex("}") + 1])
        return bool(d["verdict"]), d.get("reason", "")
    except Exception:
        return False, f"unparseable judge output: {text[:150]}"


def judge_correctness(question: str, answer: str, reference: str) -> tuple[bool, str]:
    """Reference-based correctness: grade the answer against the ground-truth
    reference, NOT the judge's own knowledge."""
    return _ask(
        "You are grading an answer against a REFERENCE answer that is known to be correct.\n\n"
        f"Question: {question}\n\nReference (ground truth): {reference}\n\nAnswer to grade: {answer}\n\n"
        "Is the answer consistent with the reference and responsive to the question? "
        "It may be phrased differently or be terse, but must not contradict or omit key facts "
        "from the reference. "
        'Reply ONLY JSON: {"verdict": true or false, "reason": "<one sentence>"}'
    )


def judge_groundedness(answer: str, context: str) -> tuple[bool, str]:
    """RAG faithfulness: is every factual claim in the answer supported by the
    retrieved context? Flags hallucination independent of correctness."""
    return _ask(
        "You are checking whether an answer is GROUNDED in the retrieved context.\n\n"
        f"Retrieved context:\n{context}\n\nAnswer: {answer}\n\n"
        "Is every factual claim in the answer supported by the context above? "
        "If the answer states facts not present in the context, it is NOT grounded. "
        'Reply ONLY JSON: {"verdict": true or false, "reason": "<one sentence>"}'
    )

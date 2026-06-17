"""Custom input+output security guardrail for the LiteLLM gateway.

Runs in-process at the choke point (no external Presidio/Lakera service) on
every request, both directions:

  pre_call  — block prompt injection (400); redact PII before it reaches the model
  post_call — redact PII AND credential shapes the model emits, before the
              reply reaches the caller

Because this lives at the gateway, every app that routes through it is covered
by one policy — the security half of the same choke point that does cost/keys.

Redactions and blocks are logged HERE (deterministic gateway-side audit), so
you can confirm a control fired without relying on the model's (non-deterministic)
output to reveal it.

Registered in litellm_config.yaml:
  guardrails:
    - guardrail_name: sandbox-guard
      litellm_params:
        guardrail: guardrails.SandboxGuardrail
        mode: ["pre_call", "post_call"]
        default_on: true
"""
import logging
import re

from fastapi import HTTPException
from litellm.integrations.custom_guardrail import CustomGuardrail

# Dedicated logger with its own handler so the audit always appears in the
# gateway output regardless of the host's logging config.
_log = logging.getLogger("sandbox.guardrail")
if not _log.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("%(asctime)s [guardrail] %(message)s"))
    _log.addHandler(_h)
    _log.setLevel(logging.INFO)
    _log.propagate = False

_INJECTION = re.compile(
    "|".join([
        r"ignore\s+(all\s+)?(previous|prior)\s+instructions",
        r"disregard\s+(your|the)\s+(system\s+)?(prompt|instructions)",
        r"reveal\s+your\s+(system\s+)?prompt",
        r"override\s+your\s+instructions",
        r"you\s+are\s+now\s+(a|an|in)\b",
    ]),
    re.IGNORECASE,
)

# Ordered: redact longer/structured matches before looser ones.
_PII = [
    ("EMAIL", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    ("CREDIT_CARD", re.compile(r"\b(?:\d[ -]?){13,19}\b")),
    ("SSN", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("PHONE", re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b")),
]

# Output-specific: credential shapes the model might emit.
_SECRETS = [
    ("API_KEY", re.compile(r"\b(?:sk-[A-Za-z0-9]{16,}|AIza[0-9A-Za-z_\-]{30,})\b")),
]


def _redact(text: str, patterns=_PII) -> tuple[str, dict]:
    """Redact matches; return (redacted_text, {label: count}) for auditing."""
    hits: dict[str, int] = {}
    for label, rx in patterns:
        text, n = rx.subn(f"[REDACTED_{label}]", text)
        if n:
            hits[label] = hits.get(label, 0) + n
    return text, hits


class SandboxGuardrail(CustomGuardrail):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    async def async_pre_call_hook(self, user_api_key_dict, cache, data, call_type):
        for msg in data.get("messages", []):
            if msg.get("role") != "user" or not isinstance(msg.get("content"), str):
                continue
            if _INJECTION.search(msg["content"]):
                _log.warning("BLOCKED request: prompt-injection pattern in input")
                raise HTTPException(
                    status_code=400,
                    detail="Blocked by gateway guardrail: prompt-injection pattern detected",
                )
            redacted, hits = _redact(msg["content"])
            if hits:
                _log.info("redacted PII from input: %s", hits)
            msg["content"] = redacted
        return data

    async def async_post_call_success_hook(self, data, user_api_key_dict, response):
        for choice in getattr(response, "choices", []):
            msg = getattr(choice, "message", None)
            content = getattr(msg, "content", None)
            if not isinstance(content, str):
                continue
            content, pii_hits = _redact(content)
            content, secret_hits = _redact(content, _SECRETS)
            hits = {**pii_hits, **secret_hits}
            if hits:
                _log.info("redacted from output: %s", hits)
            msg.content = content
        return response

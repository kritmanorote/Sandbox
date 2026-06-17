"""Custom input guardrail for the LiteLLM gateway.

Runs in-process at the choke point (no external Presidio/Lakera service) on
every request, before it reaches the model. Two defenses:

  1. Prompt-injection block — reject requests containing known injection
     patterns ("ignore previous instructions", etc.).
  2. PII redaction — strip emails / phones / cards / SSNs from user messages
     so they never leave to the model provider.

Because this lives at the gateway, every app behind it is covered by one
policy — the security half of the same choke point that does cost/keys.

Registered in litellm_config.yaml:
  guardrails:
    - guardrail_name: sandbox-input-guard
      litellm_params:
        guardrail: guardrails.SandboxGuardrail
        mode: pre_call
        default_on: true
"""
import re

from fastapi import HTTPException
from litellm.integrations.custom_guardrail import CustomGuardrail

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

# Output-specific: credential shapes the model might emit (from context,
# training, or hallucination). Caught on the response side, not the request.
_SECRETS = [
    ("API_KEY", re.compile(r"\b(?:sk-[A-Za-z0-9]{16,}|AIza[0-9A-Za-z_\-]{30,})\b")),
]


def _redact(text: str, patterns=_PII) -> str:
    for label, rx in patterns:
        text = rx.sub(f"[REDACTED_{label}]", text)
    return text


class SandboxGuardrail(CustomGuardrail):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    async def async_pre_call_hook(self, user_api_key_dict, cache, data, call_type):
        for msg in data.get("messages", []):
            if msg.get("role") != "user" or not isinstance(msg.get("content"), str):
                continue
            if _INJECTION.search(msg["content"]):
                # Block: reject the request before it reaches the model.
                raise HTTPException(
                    status_code=400,
                    detail="Blocked by gateway guardrail: prompt-injection pattern detected",
                )
            # Transform: redact PII so it never leaves to the provider.
            msg["content"] = _redact(msg["content"])
        return data

    async def async_post_call_success_hook(self, data, user_api_key_dict, response):
        # Response side of the choke point: redact PII AND credential shapes the
        # model emits, before the reply reaches the caller. Defense in depth —
        # the model can produce sensitive data even when the input was clean.
        for choice in getattr(response, "choices", []):
            msg = getattr(choice, "message", None)
            content = getattr(msg, "content", None)
            if isinstance(content, str):
                msg.content = _redact(_redact(content), _SECRETS)
        return response

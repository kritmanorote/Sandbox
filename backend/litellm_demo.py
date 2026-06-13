"""AI-gateway concept demo using LiteLLM as a library (no proxy server, no DB).

Demonstrates the three gateway values that a real proxy would centralize:
  1. Provider abstraction — app code is OpenAI-shaped; the model string is the
     only thing naming Gemini. Swap to "openai/gpt-4o" or "anthropic/..." and
     the rest is unchanged.
  2. Credential containment — the app passes one key to one call site, not the
     Gemini SDK sprinkled across the codebase.
  3. Cost visibility — with model pricing registered, LiteLLM computes a per-call
     cost the gateway would attribute to a team/key.

Run:  backend/.venv/Scripts/python.exe backend/litellm_demo.py
"""
import os

from dotenv import load_dotenv

load_dotenv()

import litellm

# Register pricing for a model not in LiteLLM's built-in cost map, so
# response_cost is computed instead of None — this is the per-token rate a
# gateway would use for chargeback.
litellm.register_model({
    "gemini/gemini-3.1-flash-lite": {
        "input_cost_per_token": 0.0000001,
        "output_cost_per_token": 0.0000004,
        "litellm_provider": "gemini",
        "mode": "chat",
    }
})

# OpenAI-shaped call — provider-agnostic on the app side.
resp = litellm.completion(
    model="gemini/gemini-3.1-flash-lite",
    messages=[{"role": "user", "content": "How many ghosts are in Pac-Man? One sentence."}],
    api_key=os.environ["GEMINI_API_KEY"],
)

print("=== response (OpenAI response shape, content from Gemini) ===")
print(resp.choices[0].message.content.strip())

usage = resp.usage
print("\n=== what a gateway would record ===")
print(f"model routed to : {resp.model}")
print(f"prompt tokens   : {usage.prompt_tokens}")
print(f"output tokens   : {usage.completion_tokens}")
print(f"response cost   : ${resp._hidden_params.get('response_cost')}")

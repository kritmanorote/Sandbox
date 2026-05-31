"""Exchange log helpers — UI observability only, no agent logic here.

Pulled out so /chat and /chat-langchain in main.py can stay focused on the
actual flow without log-append noise. Both helpers produce entries in the
respective SDK's native shape (no synthetic fields).
"""
from typing import Any
import json

import google.generativeai as genai
from langchain_core.messages import AIMessage


class LoggedChatSession:
    """Wraps a genai.ChatSession, recording every request and response as
    flat {role, parts} entries — the Gemini SDK's native Content shape."""

    def __init__(self, model: genai.GenerativeModel, history: list[dict]):
        self.session = model.start_chat(history=history)
        # Seed the log with prior history so the conversation is complete.
        self.log: list[dict] = [
            {"role": m["role"], "parts": [{"text": p} for p in m["parts"]]}
            for m in history
        ]

    def send_text(self, text: str):
        """Send a plain user message; record both sides."""
        self.log.append({"role": "user", "parts": [{"text": text}]})
        response = self.session.send_message(text)
        self._log_model_response(response)
        return response

    def send_function_response(self, name: str, response_data: dict):
        """Send a function result back to the model; record both sides."""
        self.log.append({
            "role": "user",
            "parts": [{"function_response": {"name": name, "response": response_data}}],
        })
        response = self.session.send_message(
            genai.protos.Content(parts=[genai.protos.Part(
                function_response=genai.protos.FunctionResponse(
                    name=name, response=response_data
                )
            )])
        )
        self._log_model_response(response)
        return response

    def _log_model_response(self, response):
        parts_data: list[dict] = []
        for p in response.candidates[0].content.parts:
            if p.function_call.name:
                parts_data.append({"function_call": {
                    "name": p.function_call.name,
                    "args": dict(p.function_call.args),
                }})
            elif p.text:
                parts_data.append({"text": p.text})
        self.log.append({"role": "model", "parts": parts_data})


def summarize_langchain_result(result: dict) -> tuple[str, list[dict], list[dict]]:
    """Unpack a LangChain agent.invoke() result into (reply, tool_calls, exchange_log).

    - reply: text of the final AIMessage (handles both str and content-block list)
    - tool_calls: [{query, results}] for the cyan agent pill in the UI
    - exchange_log: raw model_dump() of every message (the message log)
    """
    reply = ""
    tool_calls: list[dict] = []
    for msg in result["messages"]:
        if isinstance(msg, AIMessage):
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    tool_calls.append({"query": tc["args"].get("query", ""), "results": []})
            elif msg.content:
                if isinstance(msg.content, str):
                    reply = msg.content
                elif isinstance(msg.content, list):
                    # ChatGoogleGenerativeAI returns content blocks after a tool call
                    reply = "".join(
                        b.get("text", "") for b in msg.content
                        if isinstance(b, dict) and b.get("type") == "text"
                    )
                else:
                    reply = str(msg.content)

    # Attach tool results from ToolMessages to the matching tool_calls entry by order.
    tool_msg_idx = 0
    for msg in result["messages"]:
        if msg.__class__.__name__ == "ToolMessage" and tool_msg_idx < len(tool_calls):
            content: Any = msg.content
            if isinstance(content, str):
                try:
                    content = json.loads(content)
                except Exception:
                    content = [content]
            tool_calls[tool_msg_idx]["results"] = content if isinstance(content, list) else [str(content)]
            tool_msg_idx += 1

    exchange_log = [msg.model_dump() for msg in result["messages"]]
    return reply, tool_calls, exchange_log

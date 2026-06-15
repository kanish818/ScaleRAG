"""
LLM Service — Groq primary, Gemini fallback.
Streaming SSE via Groq llama-3.3-70b-versatile.
Auto-retries with Gemini fallback on Groq failure.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Generator, List

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GEMINI_GENERATE_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-1.5-flash:streamGenerateContent?alt=sse&key={key}"
)

SYSTEM_PROMPT = """\
You are ScaleRAG, a production-grade document intelligence assistant.

Answer ONLY using the document excerpts provided below.
If the excerpts do not contain enough information, say:
"I could not find this information in the provided documents."

Rules:
- Be concise and factual.
- Cite sources inline as [filename, Page X].
- Never fabricate information not present in the excerpts.
- Treat chat history as conversational context only.
- If history conflicts with excerpts, rely on excerpts.

--- DOCUMENT EXCERPTS ---
{context}
--- END EXCERPTS ---
"""


def _build_context(chunks: List[Dict[str, Any]]) -> str:
    if not chunks:
        return "No relevant excerpts found."
    parts = []
    for c in chunks:
        parts.append(
            f"[{c.get('filename', 'unknown')}, Page {c.get('page_num', '?')}]\n"
            f"{c.get('text', '').strip()}"
        )
    return "\n\n".join(parts)


def _groq_stream(
    messages: List[Dict[str, str]],
) -> Generator[str, None, None]:
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": messages,
        "stream": True,
        "temperature": 0.3,
        "max_tokens": 2048,
    }
    headers = {
        "Authorization": f"Bearer {settings.GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=httpx.Timeout(120.0, connect=15.0)) as client:
        with client.stream("POST", GROQ_URL, headers=headers, json=payload) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line or not line.startswith("data: "):
                    continue
                data = line[6:].strip()
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                    content = (chunk.get("choices") or [{}])[0].get("delta", {}).get("content")
                    if content:
                        yield content
                except json.JSONDecodeError:
                    continue


def _gemini_stream(
    messages: List[Dict[str, str]],
) -> Generator[str, None, None]:
    """Gemini 1.5 Flash fallback."""
    # Convert OpenAI-format messages to Gemini format
    contents = []
    for msg in messages:
        role = "user" if msg["role"] in ("user", "system") else "model"
        contents.append({"role": role, "parts": [{"text": msg["content"]}]})

    url = GEMINI_GENERATE_URL.format(key=settings.GEMINI_API_KEY)
    payload = {"contents": contents, "generationConfig": {"temperature": 0.3, "maxOutputTokens": 2048}}

    with httpx.Client(timeout=httpx.Timeout(120.0, connect=15.0)) as client:
        with client.stream("POST", url, json=payload) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line or not line.startswith("data: "):
                    continue
                data = line[6:].strip()
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                    candidates = chunk.get("candidates") or []
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        for part in parts:
                            text = part.get("text", "")
                            if text:
                                yield text
                except json.JSONDecodeError:
                    continue


def stream_chat(
    question: str,
    context_chunks: List[Dict[str, Any]],
    chat_history: List[Dict[str, str]],
) -> Generator[str, None, None]:
    context = _build_context(context_chunks)
    system_prompt = SYSTEM_PROMPT.format(context=context)

    messages = [{"role": "system", "content": system_prompt}]
    for msg in chat_history:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": question})

    # Try Groq first, fall back to Gemini
    try:
        logger.info("Streaming via Groq (primary LLM).")
        yield from _groq_stream(messages)
    except Exception as groq_exc:
        logger.warning("Groq failed (%s) — falling back to Gemini.", groq_exc)
        try:
            yield from _gemini_stream(messages)
        except Exception as gemini_exc:
            logger.error("Both LLMs failed. Groq: %s | Gemini: %s", groq_exc, gemini_exc)
            yield f"\n\n[Service temporarily unavailable. Please try again. Error: {gemini_exc}]"

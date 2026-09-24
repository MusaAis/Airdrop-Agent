import asyncio
import httpx
import logging
from backend.ai.key_pool import groq_pool

logger = logging.getLogger("airdrop.ai.groq")
GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"

_MAX_RETRIES = 4   # tries across all available keys before giving up


async def ask_groq(
    system_prompt: str,
    user_prompt: str,
    model: str = "llama-3.3-70b-versatile",
    temperature: float = 0.2,
    max_tokens: int = 4096,
) -> str:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    last_exc: Exception = None
    for attempt in range(_MAX_RETRIES):
        key = await groq_pool.get()
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                resp = await client.post(GROQ_CHAT_URL, json=payload, headers=headers)
                if resp.status_code == 429:
                    await groq_pool.mark_429(key)
                    last_exc = Exception(f"Groq 429 on key ...{key[-6:]}")
                    continue
                resp.raise_for_status()
                return resp.json()["choices"][0]["message"]["content"]
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    await groq_pool.mark_429(key)
                    last_exc = e
                    continue
                logger.error("Groq HTTP error: %s", e)
                raise
            except Exception as e:
                logger.error("Groq error (attempt %d): %s", attempt + 1, e)
                last_exc = e
                if attempt < _MAX_RETRIES - 1:
                    await asyncio.sleep(2 ** attempt)

    raise Exception(f"Groq failed after {_MAX_RETRIES} attempts: {last_exc}")

import httpx
import logging
from backend.ai.key_pool import gemini_pool

logger = logging.getLogger("airdrop.ai.gemini")

GEMINI_MODELS = [
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "gemini-1.5-pro",
]
_GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/models"

_MAX_RETRIES = 4


async def ask_gemini(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.2,
    max_tokens: int = 4096,
) -> str:
    payload = {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
        },
    }

    last_exc: Exception = None
    for attempt in range(_MAX_RETRIES):
        key = await gemini_pool.get()
        headers = {"x-goog-api-key": key, "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=90.0) as client:
            for model in GEMINI_MODELS:
                url = f"{_GEMINI_BASE}/{model}:generateContent"
                try:
                    resp = await client.post(url, json=payload, headers=headers)
                    if resp.status_code == 404:
                        logger.debug("Gemini model %s not available, trying next", model)
                        continue
                    if resp.status_code == 429:
                        await gemini_pool.mark_429(key)
                        last_exc = Exception(f"Gemini 429 on key ...{key[-6:]} model {model}")
                        break  # try next key
                    resp.raise_for_status()
                    data = resp.json()
                    return data["candidates"][0]["content"]["parts"][0]["text"]
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 404:
                        continue
                    if e.response.status_code == 429:
                        await gemini_pool.mark_429(key)
                        last_exc = e
                        break
                    logger.error("Gemini HTTP error (%s): %s", model, e)
                    raise
                except Exception as e:
                    logger.error("Gemini error (%s attempt %d): %s", model, attempt + 1, e)
                    last_exc = e
                    raise

    raise Exception(f"Gemini failed after {_MAX_RETRIES} attempts: {last_exc}")

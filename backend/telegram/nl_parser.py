import json
import re
import logging
from backend.ai.gemini_client import ask_gemini
from backend.ai.groq_client import ask_groq
from backend.ai.prompts import prompt_telegram_cmd

logger = logging.getLogger("airdrop.telegram.nl_parser")


def extract_json(text: str) -> str:
    """Extract a JSON object or array from raw LLM text."""
    cleaned = re.sub(r"```(?:json)?\s*", "", text).replace("```", "")
    start = min(
        (cleaned.find("{") if cleaned.find("{") != -1 else len(cleaned)),
        (cleaned.find("[") if cleaned.find("[") != -1 else len(cleaned)),
    )
    end = max(cleaned.rfind("}"), cleaned.rfind("]"))
    if start < len(cleaned) and end != -1:
        return cleaned[start : end + 1]
    return cleaned


async def parse_natural_language(message: str) -> dict:
    """
    Route natural language Telegram messages → structured action dict.

    Primary:  Gemini (gemini-2.0-flash) — higher free-tier RPM, keeps Groq
              budget free for the structured AI tasks (risk, criteria, etc.)
    Fallback: Groq  — used only if Gemini fails entirely.
    """
    system = (
        "You are a strict JSON-only command router for an airdrop farming bot. "
        "Always output valid JSON and nothing else — no markdown, no explanation."
    )
    user_prompt = prompt_telegram_cmd(message)

    # ── Primary: Gemini ──────────────────────────────────────────────────────
    try:
        response = await ask_gemini(system, user_prompt, temperature=0.0)
        json_str = extract_json(response)
        parsed = json.loads(json_str)
        logger.debug("NL parsed via Gemini: action=%s", parsed.get("action"))
        return parsed
    except json.JSONDecodeError:
        logger.error("Gemini NL: JSON decode failed. Raw: %.300s", response)
    except Exception as e:
        logger.warning("Gemini NL failed (%s), falling back to Groq", e)

    # ── Fallback: Groq ───────────────────────────────────────────────────────
    try:
        response = await ask_groq(system, user_prompt, temperature=0.0)
        json_str = extract_json(response)
        parsed = json.loads(json_str)
        logger.debug("NL parsed via Groq fallback: action=%s", parsed.get("action"))
        return parsed
    except json.JSONDecodeError:
        logger.error("Groq NL: JSON decode failed. Raw: %.300s", response)
        return {
            "action": "error",
            "parameters": {},
            "requires_confirmation": False,
            "clarification_needed": "AI returned invalid JSON — please rephrase.",
        }
    except Exception as e:
        logger.error("Both Gemini and Groq failed for NL parsing: %s", e)
        return {
            "action": "error",
            "parameters": {},
            "requires_confirmation": False,
            "clarification_needed": f"AI unavailable: {str(e)[:150]}",
        }

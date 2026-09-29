import json
import re
import logging
from sqlalchemy.ext.asyncio import AsyncSession

from backend.ai.gemini_client import ask_gemini
from backend.ai.groq_client import ask_groq
from backend.ai.prompts import prompt_telegram_cmd
from backend.telegram.entity_resolver import build_entity_index
from backend.telegram.conversation import get_context_block

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


async def parse_natural_language(
    message: str,
    db: AsyncSession = None,
    user_id: int = None,
) -> dict:
    """
    Route natural language Telegram messages → structured action dict.

    Primary:  Gemini (gemini-2.0-flash) — higher free-tier RPM, keeps Groq
              budget free for the structured AI tasks (risk, criteria, etc.)
    Fallback: Groq  — used only if Gemini fails entirely.

    Phase 4 additions:
      - db: if provided, an entity index (wallets/projects/chains by
        id/name/tag) is built and injected so the model can resolve
        references like "my main wallet" to a real id. Optional and
        backward-compatible — omitting db just skips this section, same
        behavior as before Phase 4.
      - user_id: if provided (together with db), recent conversation turns
        for this user are injected so a follow-up like "make it 10" can
        complete the previous command. Also optional/backward-compatible.

    Entity resolution of the LLM's OUTPUT (turning a fuzzy name back into a
    numeric id post-parse) is a separate step — see
    telegram/entity_resolver.resolve_entities() — deliberately not done here,
    so this function's contract (raw message in, parsed dict out) stays
    simple and testable without a DB session for the common case.
    """
    system = (
        "You are a strict JSON-only command router for an airdrop farming bot. "
        "Always output valid JSON and nothing else — no markdown, no explanation."
    )

    entity_index = ""
    if db is not None:
        try:
            entity_index = await build_entity_index(db)
        except Exception as e:
            logger.warning("Could not build entity index (continuing without it): %s", e)

    recent_context = ""
    if user_id is not None:
        try:
            recent_context = get_context_block(user_id)
        except Exception as e:
            logger.warning("Could not build conversation context (continuing without it): %s", e)

    user_prompt = prompt_telegram_cmd(message, entity_index=entity_index, recent_context=recent_context)

    # ── Primary: Gemini ──────────────────────────────────────────────────────
    gemini_response = None
    try:
        gemini_response = await ask_gemini(system, user_prompt, temperature=0.0)
        json_str = extract_json(gemini_response)
        parsed = json.loads(json_str)
        logger.debug("NL parsed via Gemini: action=%s", parsed.get("action"))
        return parsed
    except json.JSONDecodeError:
        logger.error("Gemini NL: JSON decode failed. Raw: %.300s", gemini_response or "")
    except Exception as e:
        logger.warning("Gemini NL failed (%s), falling back to Groq", e)

    # ── Fallback: Groq ───────────────────────────────────────────────────────
    groq_response = None
    try:
        groq_response = await ask_groq(system, user_prompt, temperature=0.0)
        json_str = extract_json(groq_response)
        parsed = json.loads(json_str)
        logger.debug("NL parsed via Groq fallback: action=%s", parsed.get("action"))
        return parsed
    except json.JSONDecodeError:
        logger.error("Groq NL: JSON decode failed. Raw: %.300s", groq_response or "")
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

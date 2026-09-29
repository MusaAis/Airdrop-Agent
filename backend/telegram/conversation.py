"""
Short-lived conversation memory for the natural-language Telegram parser
(PLAN.md §5.1). Same in-memory-dict-with-TTL pattern already used by
_PENDING_CONFIRMATIONS (bot.py) and the project wizard — acceptable at
single-operator/testnet scale, lost on restart, no DB table needed.

Purpose: let a follow-up message like "make it 10" complete a partial
command from the previous 1-2 turns, e.g.:
  user: "set priority of project 3"
  bot:  (missing value, asks or defers)
  user: "make it 10"        <- needs to remember action=project.prioritize, id=3

We store the last N turns per user as (raw_text, parsed_action, parsed_params)
and render them into the NL prompt as RECENT CONTEXT. We deliberately do NOT
try to auto-merge turns in Python — merging is the LLM's job, since deciding
whether "make it 10" is a priority, a wallet count, or a gas multiplier
requires actually understanding the previous turn's intent. Python only
keeps the window and expires it.
"""
import time
from collections import defaultdict, deque
from typing import Deque, Dict, Optional

TURN_LIMIT = 2
TTL_SECS = 600  # 10 minutes idle -> context drops, same spirit as wizard TTL

_HISTORY: Dict[int, Deque[dict]] = defaultdict(lambda: deque(maxlen=TURN_LIMIT))
_LAST_SEEN: Dict[int, float] = {}


def record_turn(user_id: int, raw_text: str, action: str, params: dict, reply_summary: str = "") -> None:
    """Call after every parsed+dispatched NL turn (not for slash commands —
    those already carry explicit args and don't need context)."""
    now = time.monotonic()
    _LAST_SEEN[user_id] = now
    _HISTORY[user_id].append({
        "text": raw_text[:200],
        "action": action,
        "params": params,
        "reply_summary": (reply_summary or "")[:150],
        "ts": now,
    })


def get_context_block(user_id: int) -> str:
    """Render recent turns as a prompt-ready text block, or "" if none/expired."""
    last_seen = _LAST_SEEN.get(user_id)
    if last_seen is None or (time.monotonic() - last_seen) > TTL_SECS:
        _HISTORY.pop(user_id, None)
        _LAST_SEEN.pop(user_id, None)
        return ""

    turns = list(_HISTORY.get(user_id, []))
    if not turns:
        return ""

    lines = ["RECENT CONTEXT (last messages from this user, oldest first):"]
    for t in turns:
        lines.append(f'  User said: "{t["text"]}"')
        lines.append(f'  -> parsed as action={t["action"]} params={t["params"]}')
        if t["reply_summary"]:
            lines.append(f'  -> bot replied: "{t["reply_summary"]}"')
    lines.append(
        "If the CURRENT message looks like a follow-up correction or completion "
        "of the most recent turn above (e.g. providing a missing value), merge "
        "it with that turn's action instead of treating it as unrelated."
    )
    return "\n".join(lines)


def clear_context(user_id: int) -> None:
    _HISTORY.pop(user_id, None)
    _LAST_SEEN.pop(user_id, None)

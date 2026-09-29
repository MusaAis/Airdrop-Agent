"""
Fuzzy entity resolution for the natural-language Telegram parser (PLAN.md §5.1).

Two jobs:
  1. build_entity_index() — a compact summary of current wallets/projects/
     chains injected into the LLM prompt, so it can map "my main wallet" or
     "the zksync chain" to a real identifier instead of inventing one.
  2. resolve_entities() — a post-parse pass that normalizes whatever the LLM
     put in `parameters` (an id, a tag, a name, a partial address) against the
     real DB rows using fuzzy string matching. If the LLM already returned a
     valid numeric ID, this is a no-op. If it returned a name/tag that matches
     more than one candidate, we downgrade the action to "clarify" instead of
     guessing — silent wrong guesses are worse than one extra question for a
     fund-adjacent bot.

Capped at INDEX_MAX_* rows per entity type to keep the prompt small; if a
deployment exceeds that, exact numeric IDs still work, only fuzzy-by-name
degrades gracefully (falls back to "not found, use an ID").
"""
import difflib
import logging
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.models import Wallet, Project, Chain

logger = logging.getLogger("airdrop.telegram.entity_resolver")

INDEX_MAX_WALLETS = 50
INDEX_MAX_PROJECTS = 30
INDEX_MAX_CHAINS = 20

_FUZZY_CUTOFF = 0.6  # difflib similarity threshold below which we don't guess

# Actions whose params carry entity references worth resolving, and which
# param keys on each hold which entity type. Kept narrow and explicit rather
# than resolving every "id"-looking key, since some ids are validation ids,
# tx ids, etc. that have no name/tag concept at all.
_RESOLVABLE = {
    "wallet.status": [("id", "wallet")],
    "wallet.balance": [("id", "wallet")],
    "wallet.pause": [("id", "wallet")],
    "wallet.resume": [("id", "wallet")],
    "wallet.blacklist": [("id", "wallet")],
    "wallet.archive": [("id", "wallet")],
    "wallet.tag": [("id", "wallet")],
    "wallet.fund": [("id", "wallet"), ("chain_id", "chain")],
    "wallet.health": [("id", "wallet")],
    "wallet.sybil": [("id", "wallet")],
    "wallet.set_gas": [("id", "wallet")],
    "chain.enable": [("id", "chain")],
    "chain.disable": [("id", "chain")],
    "chain.status": [("id", "chain")],
    "chain.gas": [("id", "chain")],
    "chain.tokens": [("id", "chain")],
    "task.list": [("project_id", "project")],
    "task.status": [("id", "task")],
    "task.enable": [("id", "task")],
    "task.pause": [("id", "task")],
    "task.trigger": [("task_id", "task"), ("wallet_id", "wallet")],
    "project.status": [("id", "project")],
    "project.disable": [("id", "project")],
    "project.enable": [("id", "project")],
    "project.pause": [("id", "project")],
    "project.resume": [("id", "project")],
    "project.approve": [("id", "project")],
    "project.reject": [("id", "project")],
    "project.gap": [("id", "project")],
    "project.reset_circuit": [("id", "project")],
    "faucet.request": [("wallet_id", "wallet"), ("chain_id", "chain")],
    "faucet.bulk": [("chain_id", "chain")],
    "gas.price": [("chain_id", "chain")],
    "gas.refill": [("wallet_id", "wallet"), ("chain_id", "chain")],
    "report.eligibility": [("project_id", "project")],
    "report.daily_progress": [("project_id", "project")],
    "report.gas": [("chain_id", "chain")],
    "report.summary": [("project_id", "project")],
    "config.show": [("wallet_id", "wallet")],
    "config.set": [("wallet_id", "wallet")],
}


async def build_entity_index(db: AsyncSession) -> str:
    """Compact text block injected into the NL prompt under ENTITY INDEX."""
    lines = []

    wallets = (await db.execute(
        select(Wallet).where(Wallet.status != "archived").order_by(Wallet.id).limit(INDEX_MAX_WALLETS)
    )).scalars().all()
    if wallets:
        lines.append("WALLETS (id | short_address | tags):")
        for w in wallets:
            tags = ",".join(w.tags or []) or "-"
            short = f"{w.address[:6]}…{w.address[-4:]}"
            name = f" name:{w.name}" if getattr(w, "name", None) else ""
            lines.append(f"  {w.id} | {short} | {tags}{name}")

    projects = (await db.execute(
        select(Project).where(Project.status != "archived").order_by(Project.id).limit(INDEX_MAX_PROJECTS)
    )).scalars().all()
    if projects:
        lines.append("PROJECTS (id | name):")
        for p in projects:
            lines.append(f"  {p.id} | {p.name}")

    chains = (await db.execute(select(Chain).order_by(Chain.id).limit(INDEX_MAX_CHAINS))).scalars().all()
    if chains:
        lines.append("CHAINS (id | name):")
        for c in chains:
            lines.append(f"  {c.id} | {c.name}")

    if not lines:
        return "ENTITY INDEX: (empty — no wallets/projects/chains configured yet)"
    return "ENTITY INDEX (use these ids when the user refers to something by name/tag):\n" + "\n".join(lines)


def _best_match(query: str, candidates: dict) -> Optional[tuple]:
    """candidates: {id: [searchable strings]}. Returns (id, matched_str, score) or None."""
    query = query.strip().lower()
    if not query:
        return None
    best = None
    for entity_id, strings in candidates.items():
        for s in strings:
            s_l = s.lower()
            if query == s_l:
                return (entity_id, s, 1.0)
            score = difflib.SequenceMatcher(None, query, s_l).ratio()
            if best is None or score > best[2]:
                best = (entity_id, s, score)
    if best and best[2] >= _FUZZY_CUTOFF:
        return best
    return None


def _count_matches(query: str, candidates: dict) -> list:
    """Return all candidate ids whose strings are within fuzzy range, for ambiguity detection."""
    query = query.strip().lower()
    hits = []
    for entity_id, strings in candidates.items():
        for s in strings:
            score = difflib.SequenceMatcher(None, query, s.lower()).ratio()
            if score >= _FUZZY_CUTOFF or query in s.lower():
                hits.append((entity_id, s, score))
                break
    hits.sort(key=lambda x: x[2], reverse=True)
    return hits


async def _wallet_candidates(db: AsyncSession) -> dict:
    wallets = (await db.execute(select(Wallet).where(Wallet.status != "archived"))).scalars().all()
    out = {}
    for w in wallets:
        strings = [w.address, w.address[:10]]
        if w.tags:
            strings.extend(w.tags)
        if getattr(w, "name", None):
            strings.append(w.name)
        out[w.id] = strings
    return out


async def _project_candidates(db: AsyncSession) -> dict:
    projects = (await db.execute(select(Project).where(Project.status != "archived"))).scalars().all()
    return {p.id: [p.name] for p in projects}


async def _chain_candidates(db: AsyncSession) -> dict:
    chains = (await db.execute(select(Chain))).scalars().all()
    return {c.id: [c.name] for c in chains}


_CANDIDATE_FETCHERS = {
    "wallet": _wallet_candidates,
    "project": _project_candidates,
    "chain": _chain_candidates,
}


async def resolve_entities(db: AsyncSession, action: str, params: dict) -> dict:
    """
    Normalize params in place (on a copy) for the given action.
    Returns the (possibly modified) params dict, OR a dict with
    {"_clarify": "..."} if a reference was ambiguous — caller should check
    for that key and route to the "clarify" action instead of executing.
    """
    spec = _RESOLVABLE.get(action)
    if not spec:
        return params

    params = dict(params)
    for key, entity_type in spec:
        raw = params.get(key)
        if raw is None:
            continue
        raw_str = str(raw).strip()
        if not raw_str:
            continue
        # Already a clean numeric id — nothing to resolve.
        if raw_str.lstrip("-").isdigit():
            continue
        # 0x-address for a wallet — exact match path, not fuzzy.
        fetcher = _CANDIDATE_FETCHERS.get(entity_type)
        if not fetcher:
            continue
        candidates = await fetcher(db)
        if not candidates:
            continue

        if entity_type == "wallet" and raw_str.lower().startswith("0x"):
            match = None
            for wid, strings in candidates.items():
                if any(s.lower() == raw_str.lower() for s in strings):
                    match = wid
                    break
            if match is not None:
                params[key] = match
                continue

        hits = _count_matches(raw_str, candidates)
        if not hits:
            return {
                "_clarify": (
                    f"I couldn't find a {entity_type} matching '{raw_str}'. "
                    f"Try the numeric ID instead, or check /{entity_type}_list."
                )
            }
        # Ambiguous: more than one close match with similar top scores.
        top_score = hits[0][2]
        close = [h for h in hits if h[2] >= top_score - 0.08]
        if len(close) > 1:
            options = ", ".join(f"{eid} ({s})" for eid, s, _ in close[:5])
            return {
                "_clarify": (
                    f"'{raw_str}' matches more than one {entity_type}: {options}. "
                    f"Please specify the ID."
                )
            }
        params[key] = hits[0][0]

    return params

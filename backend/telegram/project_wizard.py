"""
Guided, multi-step /project_add conversation for beginner-friendly project
setup (PLAN.md §5.5). Replaces the old single-shot "project.add <name> <type>"
with a walk-through: name -> type -> chain(s) -> socials -> optional task ->
optional criteria draft.

State is kept in-memory (mirrors the existing _PENDING_CONFIRMATIONS pattern
in telegram/bot.py) — acceptable for single-operator/testnet scale. An
in-progress wizard is lost on backend restart; the user just re-runs
/project_add.

This module owns:
  - per-user wizard state (_WIZARDS)
  - step prompts and validation
  - the final commit to DB (project + optional task + optional criteria)

bot.py is responsible for routing a whitelisted user's free-text reply into
`handle_wizard_reply()` whenever that user has an active wizard, BEFORE
falling through to NL parsing.
"""
import logging
import time
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from backend.telegram.whitelist import is_whitelisted
from backend.projects.manager import create_project, create_task_config
from backend.chains.manager import list_chains, get_chain_by_chain_id

logger = logging.getLogger("airdrop.tg.project_wizard")

_WIZARD_TTL_SECS = 300  # 5 min idle timeout per step, generous for typing on mobile

# Ordered steps. "task_*" and "criteria_*" sub-steps are only visited if the
# user opts in at their gate step.
_STEPS = [
    "name",
    "type",
    "chain",
    "socials",
    "task_gate",
    "task_type",
    "task_chain",
    "task_amounts",
    "task_contract",
    "criteria_gate",
    "criteria_docs_url",
    "confirm",
]

_TASK_TYPES = ["swap", "bridge", "stake", "transfer", "provide_liquidity", "interact_contract"]
_PROJECT_TYPES = ["ecosystem", "dapp"]

# {user_id: {"step": str, "data": dict, "expires_at": float}}
_WIZARDS: dict = {}


def _new_state() -> dict:
    return {
        "step": "name",
        "data": {
            "chain_ids": [],
            "task": {},
        },
        "expires_at": time.monotonic() + _WIZARD_TTL_SECS,
    }


def has_active_wizard(user_id: int) -> bool:
    entry = _WIZARDS.get(user_id)
    if not entry:
        return False
    if time.monotonic() > entry["expires_at"]:
        _WIZARDS.pop(user_id, None)
        return False
    return True


def start_wizard(user_id: int) -> str:
    _WIZARDS[user_id] = _new_state()
    return (
        "📁 Guided project setup\n\n"
        "Step 1/5 — What's the project's name?\n"
        "(Reply 'cancel' anytime to stop.)"
    )


def cancel_wizard(user_id: int) -> None:
    _WIZARDS.pop(user_id, None)


def _touch(user_id: int):
    _WIZARDS[user_id]["expires_at"] = time.monotonic() + _WIZARD_TTL_SECS


async def handle_wizard_reply(user_id: int, text: str, db: AsyncSession) -> str:
    """
    Advance the wizard by one step using the user's free-text reply.
    Returns the next prompt (or a completion / error message).
    Caller (bot.py) must have already confirmed has_active_wizard(user_id).
    """
    if not is_whitelisted(user_id):
        return "⛔ Unauthorized"

    text = text.strip()
    if text.lower() == "cancel":
        cancel_wizard(user_id)
        return "❌ Project setup cancelled."

    state = _WIZARDS.get(user_id)
    if not state:
        return "⚠️ No active setup — use /project_add to start one."

    _touch(user_id)
    step = state["step"]
    data = state["data"]

    try:
        if step == "name":
            if not text:
                return "Please enter a project name."
            data["name"] = text
            state["step"] = "type"
            return (
                "Step 2/5 — What type of project is this?\n"
                f"Reply with one of: {', '.join(_PROJECT_TYPES)}"
            )

        if step == "type":
            choice = text.lower()
            if choice not in _PROJECT_TYPES:
                return f"Please reply with one of: {', '.join(_PROJECT_TYPES)}"
            data["type"] = choice
            state["step"] = "chain"
            chains = await list_chains(db)
            if not chains:
                data["chain_ids"] = []
                state["step"] = "socials"
                return (
                    "⚠️ No chains are configured yet, so I'll skip chain selection "
                    "(add one later via /chain_add or the dashboard).\n\n"
                    "Step 4/5 — Website, Twitter, and Discord? "
                    "Reply with each on its own line, or 'skip' to leave them blank."
                )
            chain_list = "\n".join(f"  • {c.name} (id {c.chain_id})" for c in chains)
            return (
                f"Step 3/5 — Which chain(s) is this project on?\n{chain_list}\n\n"
                "Reply with chain IDs separated by commas (e.g. 1,56), or 'skip'."
            )

        if step == "chain":
            if text.lower() != "skip":
                ids = []
                for part in text.split(","):
                    part = part.strip()
                    if not part:
                        continue
                    try:
                        cid = int(part)
                    except ValueError:
                        return f"'{part}' isn't a number. Reply with chain IDs separated by commas, or 'skip'."
                    chain = await get_chain_by_chain_id(db, cid)
                    if not chain:
                        return f"No configured chain has ID {cid}. Check /chain_list and try again, or 'skip'."
                    ids.append(chain.id)  # store internal DB id, not the public chain_id
                data["chain_ids"] = ids
            state["step"] = "socials"
            return (
                "Step 4/5 — Website, Twitter, and Discord?\n"
                "Reply with each on its own line, or 'skip' to leave them blank."
            )

        if step == "socials":
            if text.lower() != "skip":
                lines = [l.strip() for l in text.splitlines() if l.strip()]
                if len(lines) >= 1:
                    data["website"] = lines[0]
                if len(lines) >= 2:
                    data["twitter"] = lines[1]
                if len(lines) >= 3:
                    data["discord"] = lines[2]
            state["step"] = "task_gate"
            return (
                "Step 5/5 — Add a farming task now?\n"
                "Reply 'yes' to configure one now, or 'no' to add one later "
                "via /task_list or the dashboard."
            )

        if step == "task_gate":
            if text.lower() not in ("yes", "y", "no", "n"):
                return "Please reply 'yes' or 'no'."
            if text.lower() in ("no", "n"):
                state["step"] = "criteria_gate"
                return (
                    "Want to add eligibility criteria now?\n"
                    "If the project has public docs, reply with the docs URL and I'll save it "
                    "so you can draft criteria with AI on the dashboard (you review before anything is saved) — or reply 'skip'."
                )
            state["step"] = "task_type"
            return f"Task type? Reply with one of: {', '.join(_TASK_TYPES)}"

        if step == "task_type":
            choice = text.lower()
            if choice not in _TASK_TYPES:
                return f"Please reply with one of: {', '.join(_TASK_TYPES)}"
            data["task"]["task_type"] = choice
            state["step"] = "task_chain"
            return "Which chain ID should this task run on? (e.g. 1)"

        if step == "task_chain":
            try:
                cid = int(text)
            except ValueError:
                return "Please reply with a numeric chain ID (e.g. 1)."
            chain = await get_chain_by_chain_id(db, cid)
            if not chain:
                return f"No configured chain has ID {cid}. Check /chain_list and try again."
            data["task"]["chain_id"] = chain.id
            state["step"] = "task_amounts"
            return (
                "Min and max amount for this task, comma separated "
                "(e.g. 0.01,0.05)?"
            )

        if step == "task_amounts":
            parts = [p.strip() for p in text.split(",")]
            if len(parts) != 2:
                return "Reply with two numbers separated by a comma, e.g. 0.01,0.05"
            try:
                min_amt, max_amt = float(parts[0]), float(parts[1])
            except ValueError:
                return "Both values must be numbers, e.g. 0.01,0.05"
            if min_amt <= 0 or max_amt < min_amt:
                return "max_amount must be >= min_amount, and both must be > 0. Try again."
            data["task"]["min_amount"] = min_amt
            data["task"]["max_amount"] = max_amt
            state["step"] = "task_contract"
            return (
                "Contract address for this task (router/staking/bridge contract), "
                "or 'skip' if you'll fill this in later via the dashboard."
            )

        if step == "task_contract":
            if text.lower() != "skip":
                if not (text.startswith("0x") and len(text) == 42):
                    return "That doesn't look like a valid contract address (expected 0x + 40 hex chars). Try again, or 'skip'."
                # Store generically; task-type-specific param name is resolved at commit time.
                data["task"]["contract_address"] = text
            state["step"] = "criteria_gate"
            return (
                "Want to add eligibility criteria now?\n"
                "If the project has public docs, reply with the docs URL and I'll save it "
                "so you can draft criteria with AI on the dashboard (you review before anything is saved) — or reply 'skip'."
            )

        if step == "criteria_gate":
            if text.lower() != "skip":
                data["criteria_docs_url"] = text
            state["step"] = "confirm"
            return _render_summary(data)

        if step == "confirm":
            if text.lower() not in ("confirm", "yes", "y"):
                return "Reply 'confirm' to create the project, or 'cancel' to abort."
            result = await _commit(db, data)
            cancel_wizard(user_id)
            return result

    except Exception as e:
        logger.exception("Wizard error at step=%s user=%s", step, user_id)
        cancel_wizard(user_id)
        return f"❌ Something went wrong ({e}). Setup cancelled — please try /project_add again."

    # Unreachable, but keeps mypy/logic honest
    cancel_wizard(user_id)
    return "⚠️ Setup state lost — please try /project_add again."


def _render_summary(data: dict) -> str:
    lines = ["📋 Review your project", "", f"Name: {data.get('name')}", f"Type: {data.get('type')}"]
    if data.get("chain_ids"):
        lines.append(f"Chains: {len(data['chain_ids'])} selected")
    for key in ("website", "twitter", "discord"):
        if data.get(key):
            lines.append(f"{key.capitalize()}: {data[key]}")
    task = data.get("task") or {}
    if task:
        lines.append("")
        lines.append(
            f"Task: {task.get('task_type')} on chain_id {task.get('chain_id')} "
            f"({task.get('min_amount')}–{task.get('max_amount')})"
        )
        if task.get("contract_address"):
            lines.append(f"Contract: {task['contract_address']}")
    if data.get("criteria_docs_url"):
        lines.append("")
        lines.append(f"Docs URL (saved to notes): {data['criteria_docs_url']}")
    lines.append("")
    lines.append("Reply 'confirm' to create, or 'cancel' to abort.")
    return "\n".join(lines)


# Maps a task type to the parameter key its build_transaction_params()
# implementation expects for a bare contract address (see backend/tasks/*.py).
_CONTRACT_PARAM_BY_TASK_TYPE = {
    "swap": "router_address",
    "bridge": "bridge_contract",
    "stake": "staking_contract",
    "provide_liquidity": "router_address",
    "interact_contract": "contract_address",
    # "transfer" has no single contract param — to_address is set separately
    # and isn't part of this guided flow; left for manual dashboard config.
}


async def _commit(db: AsyncSession, data: dict) -> str:
    project = await create_project(
        db,
        name=data["name"],
        type=data["type"],
        chain_ids=data.get("chain_ids", []),
        website=data.get("website"),
        twitter=data.get("twitter"),
        discord=data.get("discord"),
        notes=(f"Docs URL: {data['criteria_docs_url']}" if data.get("criteria_docs_url") else None),
    )

    msg_lines = [f"✅ Project '{project.name}' created (ID: {project.id})."]

    task = data.get("task")
    if task and task.get("task_type") and task.get("chain_id"):
        params = {}
        contract_addr = task.get("contract_address")
        param_key = _CONTRACT_PARAM_BY_TASK_TYPE.get(task["task_type"])
        if contract_addr and param_key:
            params[param_key] = contract_addr
        task_config = await create_task_config(
            db,
            project_id=project.id,
            task_type=task["task_type"],
            chain_id=task["chain_id"],
            parameters=params,
            frequency_mins=120,
            min_amount=task["min_amount"],
            max_amount=task["max_amount"],
            enabled=bool(contract_addr),  # leave disabled if contract wasn't given yet
        )
        note = "" if contract_addr else " (disabled — add a contract address via the dashboard, then enable it)"
        msg_lines.append(f"✅ Task '{task['task_type']}' added (ID: {task_config.id}){note}.")

    docs_url = data.get("criteria_docs_url")
    if docs_url:
        msg_lines.append(
            "\n📎 Docs URL saved to the project's notes. To draft criteria with AI, open the "
            f"dashboard at /projects/new?project={project.id} — you review the draft before "
            "anything is saved."
        )

    msg_lines.append(f"\nUse /project_status {project.id} to check on it anytime.")
    return "\n".join(msg_lines)

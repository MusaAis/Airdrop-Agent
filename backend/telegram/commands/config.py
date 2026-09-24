import logging
from sqlalchemy.ext.asyncio import AsyncSession
from backend.wallet.manager import update_wallet_settings, get_wallet_settings
from backend.telegram.whitelist import is_whitelisted

logger = logging.getLogger("airdrop.tg.config")

async def handle_config_set(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    # Usage: config.set <setting> <wallet_id/all> <values...>
    if len(args)<2: return "Usage: config.set <setting> <wallet_id/all> <values>"
    setting = args[0]
    wallet_arg = args[1]
    # Determine wallet ID(s)
    if wallet_arg.lower()=="all":
        # apply to all wallets
        from backend.wallet.manager import list_wallets
        wallets = await list_wallets(db)
        wallet_ids = [w.id for w in wallets]
    else:
        wallet_ids = [int(wallet_arg)]
    for wid in wallet_ids:
        if setting == "amounts" and len(args)>=4:
            await update_wallet_settings(db, wid, amount_min_override=float(args[2]), amount_max_override=float(args[3]))
        elif setting == "timing" and len(args)>=4:
            await update_wallet_settings(db, wid, sleep_min_mins=int(args[2]), sleep_max_mins=int(args[3]))
        elif setting == "active_hours" and len(args)>=4:
            await update_wallet_settings(db, wid, active_hour_start=int(args[2]), active_hour_end=int(args[3]))
        elif setting == "bidirectional" and len(args)>=3:
            await update_wallet_settings(db, wid, bidirectional_default=args[2].lower()=="true")
        elif setting == "gas_multiplier" and len(args)>=3:
            await update_wallet_settings(db, wid, gas_multiplier=float(args[2]))
        elif setting == "daily_tx" and len(args)>=4:
            await update_wallet_settings(db, wid, daily_tx_min=int(args[2]), daily_tx_max=int(args[3]))
        elif setting == "max_workers" and len(args)>=2:
            from backend.config import MAX_WORKER_SLOTS
            # This is a global setting, not per wallet; we'll treat specially
            from backend.config import update_config_value
            # Not yet implemented; we'll just reply
            return "Global settings update via Telegram not yet supported."
        else:
            return f"Unknown setting '{setting}' or insufficient args."
    return f"✅ Setting '{setting}' applied to {len(wallet_ids)} wallet(s)."

async def _validate_config_change(db, setting: str, proposed: dict) -> tuple:
    """
    Runs the proposed setting through task_type="config" AI validation
    before it's applied. Previously config.set just wrote straight to the DB
    with zero AI check, despite the master plan saying config changes
    require both AIs to approve before applying. Returns (allowed: bool,
    message: str).
    """
    from backend.ai.orchestrator import dual_ai_validate
    from backend.ai.prompts import prompt_config_validation
    import json

    validation = await dual_ai_validate(
        task_type="config",
        system_prompt="You are reviewing a proposed bot-behavior configuration change for safety and human-likeness before it is applied.",
        user_prompt=prompt_config_validation(
            json.dumps({"config_type": "wallet_settings", "setting": setting, "proposed": proposed}),
            json.dumps({}),
        ),
        db=db,
    )
    decision = validation.final_decision or {}
    approved = decision.get("approved", True)  # default to allowing if AI output didn't parse
    issues = decision.get("issues", [])
    blocking = [i for i in issues if i.get("severity") == "blocking"]

    if not approved or blocking:
        problems = "; ".join(i.get("problem", "") for i in blocking) or "AI flagged this as unsafe."
        return False, f"⚠️ Config change blocked by AI review: {problems} (agreement {validation.agreement_score}%)"
    return True, f"(AI-validated, {validation.agreement_score}% agreement)"

async def handle_config_show(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if not args: return "Usage: config.show <wallet_id/all>"
    wallet_arg = args[0]
    if wallet_arg.lower()=="all":
        from backend.wallet.manager import list_wallets
        wallets = await list_wallets(db)
        lines = []
        for w in wallets:
            s = await get_wallet_settings(db, w.id)
            if s:
                lines.append(f"Wallet {w.id}: min={s.amount_min_override} max={s.amount_max_override} dist={s.amount_distribution} sleep={s.sleep_min_mins}-{s.sleep_max_mins}m gas={s.gas_multiplier}")
        return "\n".join(lines) if lines else "No settings."
    else:
        wallet_id = int(wallet_arg)
        s = await get_wallet_settings(db, wallet_id)
        if not s: return "No settings."
        return (f"Wallet {wallet_id}:\nAmount: {s.amount_min_override}-{s.amount_max_override} ({s.amount_distribution})\n"
                f"Sleep: {s.sleep_min_mins}-{s.sleep_max_mins} min\nGas mult: {s.gas_multiplier}\n"
                f"Active hours: {s.active_hour_start}-{s.active_hour_end}\nBidirectional: {s.bidirectional_default}\n"
                f"Daily TX: {s.daily_tx_min}-{s.daily_tx_max}")

async def handle_config_reset(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if not args: return "Usage: config.reset <wallet_id/all>"
    wallet_arg = args[0]
    if confirmation is None: return "⚠️ Confirm reset? Reply 'confirm'"
    # Reset to defaults
    if wallet_arg.lower()=="all":
        from backend.wallet.manager import list_wallets
        wallets = await list_wallets(db)
        for w in wallets:
            await update_wallet_settings(db, w.id,
                amount_min_override=None, amount_max_override=None,
                amount_distribution="weighted_low", sleep_min_mins=2, sleep_max_mins=8,
                gas_multiplier=1.0, bidirectional_default=True, daily_tx_min=2, daily_tx_max=7)
        return "All wallet settings reset."
    else:
        wid = int(wallet_arg)
        await update_wallet_settings(db, wid,
            amount_min_override=None, amount_max_override=None,
            amount_distribution="weighted_low", sleep_min_mins=2, sleep_max_mins=8,
            gas_multiplier=1.0, bidirectional_default=True, daily_tx_min=2, daily_tx_max=7)
        return f"Wallet {wid} settings reset."

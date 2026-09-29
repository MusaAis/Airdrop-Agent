import logging
from datetime import datetime, timezone
from sqlalchemy import select, func
from backend.models import Alert, Log, Transaction, Wallet, Project, TaskDailyProgress
from backend.database import async_session
from backend.telegram.sender import send_telegram_message

logger = logging.getLogger("airdrop.alerts")


async def create_and_send_alert(
    type: str,
    severity: str,
    message: str,
    wallet_id=None,
    project_id=None,
    chain_id=None,
):
    async with async_session() as db:
        alert = Alert(
            type=type,
            severity=severity,
            message=message,
            wallet_id=wallet_id,
            project_id=project_id,
            chain_id=chain_id,
            sent_telegram=False,
        )
        db.add(alert)
        await db.commit()
        await db.refresh(alert)
        try:
            icon = {"critical": "🔴", "warning": "⚠️", "info": "ℹ️"}.get(severity, "📢")
            full_msg = f"{icon} *{type.upper().replace('_', ' ')}*\n{message}"
            await send_telegram_message(full_msg, parse_mode="Markdown")
            alert.sent_telegram = True
            await db.commit()
        except Exception as e:
            logger.error(f"Failed to send Telegram alert: {e}")


async def send_daily_summary():
    """
    Full daily summary: tx stats, top wallets, eligibility, gas, upcoming
    snapshots, plus (Phase 4) an AI-narrated interpretation appended to the
    SAME message rather than sent separately. Rationale: this goes to one
    recipient once a day — a second message would just be visual noise for
    what is really one report, and it saves a round trip. If AI narration is
    unavailable (both Gemini and Groq down), the message still sends with
    just the factual section; the narrative line is simply omitted rather
    than blocking the whole daily summary.
    """
    try:
        now = datetime.now(timezone.utc)
        today = now.date().isoformat()

        async with async_session() as db:
            # Total txs today
            total_txs = (await db.execute(
                select(func.count()).select_from(Log)
                .where(Log.created_at >= now.replace(hour=0, minute=0, second=0, microsecond=0))
            )).scalar() or 0

            success_txs = (await db.execute(
                select(func.count()).select_from(Log)
                .where(
                    Log.created_at >= now.replace(hour=0, minute=0, second=0, microsecond=0),
                    Log.status == "success",
                )
            )).scalar() or 0

            failed_txs = total_txs - success_txs

            # Active wallets today
            active_wallets = (await db.execute(
                select(func.count(func.distinct(Log.wallet_id)))
                .where(Log.created_at >= now.replace(hour=0, minute=0, second=0, microsecond=0))
            )).scalar() or 0

            # Daily targets progress
            progress_rows = (await db.execute(
                select(TaskDailyProgress).where(TaskDailyProgress.date == today)
            )).scalars().all()

            targets_met = sum(1 for p in progress_rows if p.completed >= p.daily_target)
            targets_total = len(progress_rows)

            # Total gas cost today (USD)
            gas_cost = (await db.execute(
                select(func.sum(Log.gas_cost_usd))
                .where(Log.created_at >= now.replace(hour=0, minute=0, second=0, microsecond=0))
            )).scalar() or 0.0

            # Projects farming
            total_projects = (await db.execute(
                select(func.count()).select_from(Project)
                .where(Project.status == "active")
            )).scalar() or 0

            # Build message
            success_rate = round(success_txs / total_txs * 100, 1) if total_txs else 0
            msg_lines = [
                f"📊 *Daily Summary — {now.strftime('%Y-%m-%d')}*",
                "",
                f"🔄 *Transactions*",
                f"  Total: {total_txs}  ✅ {success_txs}  ❌ {failed_txs}  ({success_rate}% success)",
                f"  Active wallets: {active_wallets}",
                "",
                f"🎯 *Daily Targets*",
                f"  {targets_met}/{targets_total} wallet-task targets reached",
                "",
                f"⛽ *Gas Spent*",
                f"  ~${gas_cost:.2f} USD today",
                "",
                f"📁 *Projects*",
                f"  {total_projects} active protocols farming",
            ]

            # Phase 4: AI narrative, appended to this same message rather
            # than sent as a second one. Never let a narration failure block
            # the factual summary above — wrapped independently.
            try:
                from backend.reports.analyst import generate_daily_summary_narrative
                summary_result = await generate_daily_summary_narrative(db, hours=24)
                if summary_result["narrative"]:
                    msg_lines += [
                        "",
                        "🧠 *AI Summary*",
                        summary_result["narrative"],
                    ]
            except Exception as e:
                logger.warning(f"Daily summary: AI narration skipped ({e})")

            msg_lines += [
                "",
                "Use /report_eligibility for full breakdown, or /report_summary for this AI analysis anytime.",
            ]
            msg = "\n".join(msg_lines)
            await send_telegram_message(msg, parse_mode="Markdown")
            logger.info("Daily summary sent")

    except Exception as e:
        logger.error(f"Daily summary error: {e}")
        await send_telegram_message(f"⚠️ Daily summary failed: {e}")

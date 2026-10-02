#!/usr/bin/env python3
"""
Phase 8 patches for EXISTING files (small edits, so no full re-sends).
Run from the repo root:  python3 apply_phase8_patches.py
Each patch must match exactly once; if a file differs from what was expected the
script stops, writes nothing, and says which one. Re-running is safe.
"""
import sys
from pathlib import Path

P = []  # (path, old, new)

# ── main.py: register the telegram_routes table before init_db() ──
P.append(("backend/main.py", "import backend.core.autonomy_models",
          "import backend.telegram.topics  # noqa: F401  (registers telegram_routes table before init_db)\n"
          "import backend.core.autonomy_models"))

# ── scheduler.py: daily report now uses the new report; add weekly / monthly / AI jobs ──
S = "backend/core/scheduler.py"
P.append((S, "        from backend.telegram.alerts import send_daily_summary\n        await send_daily_summary()",
          "        from backend.reports.periodic import send_period_report\n        await send_period_report(\"daily\")"))
P.append((S, "def start_scheduler():",
          'async def _run_weekly_report():\n'
          '    try:\n'
          '        from backend.reports.periodic import send_period_report\n'
          '        await send_period_report("weekly")\n'
          '    except Exception as e:\n'
          '        logger.error(f"Weekly report error: {e}")\n\n\n'
          'async def _run_monthly_report():\n'
          '    try:\n'
          '        from backend.reports.periodic import send_period_report\n'
          '        await send_period_report("monthly")\n'
          '    except Exception as e:\n'
          '        logger.error(f"Monthly report error: {e}")\n\n\n'
          'async def _run_ai_report():\n'
          '    try:\n'
          '        from backend.reports.periodic import send_ai_report\n'
          '        await send_ai_report()\n'
          '    except Exception as e:\n'
          '        logger.error(f"AI report error: {e}")\n\n\n'
          'def start_scheduler():'))
P.append((S, "    if not sched.running:\n        sched.start()",
          '    sched.add_job(_run_ai_report,      CronTrigger(hour=8, minute=5),  id="ai_report",      replace_existing=True)\n'
          '    sched.add_job(_run_weekly_report,  CronTrigger(day_of_week="mon", hour=8, minute=10), id="weekly_report",  replace_existing=True)\n'
          '    sched.add_job(_run_monthly_report, CronTrigger(day=1, hour=8, minute=15), id="monthly_report", replace_existing=True)\n\n'
          "    if not sched.running:\n        sched.start()"))

# ── alerts.py: route each alert to its topic ──
A = "backend/telegram/alerts.py"
P.append((A, "from backend.telegram.sender import send_telegram_message",
          "from backend.telegram.sender import send_telegram_message\nfrom backend.telegram.topics import topic_for_alert"))
P.append((A, 'await send_telegram_message(full_msg, parse_mode="Markdown")',
          'await send_telegram_message(full_msg, parse_mode="Markdown", topic=topic_for_alert(type, severity))'))

# ── bot.py: register the group commands ──
B = "backend/telegram/bot.py"
P.append((B, "from backend.telegram.sender import set_bot_app",
          "from backend.telegram.sender import set_bot_app\nfrom backend.telegram.group_commands import register_group_handlers"))
P.append((B, '    app.add_handler(CommandHandler("report_summary", report_summary_cmd))',
          '    app.add_handler(CommandHandler("report_summary", report_summary_cmd))\n    register_group_handlers(app)'))

# ── help.py: list the new commands under System ──
P.append(("backend/telegram/commands/help.py", '"/system_version — Version + uptime\\n\\n"',
          '"/system_version — Version + uptime\\n"\n'
          '        "/group_setup — (run inside the group) create report topics\\n"\n'
          '        "/group_status — Where reports are being sent\\n"\n'
          '        "/report_now [daily|weekly|monthly|ai] — Send a report now\\n\\n"'))


def main():
    cache, failed = {}, False
    for path, old, new in P:
        f = Path(path)
        if not f.exists():
            print(f"MISSING  {path}"); failed = True; continue
        text = cache.get(path, f.read_text())
        if new in text and old not in text.replace(new, ""):
            print(f"skip     {path}  ({old[:40]!r} already applied)")
            cache[path] = text
            continue
        if text.count(old) != 1:
            print(f"NO MATCH {path}  expected exactly one {old[:60]!r}, found {text.count(old)}")
            failed = True; continue
        cache[path] = text.replace(old, new)
        print(f"patched  {path}  ({old[:40]!r})")
    if failed:
        print("\nSome patches failed. Nothing was written. Fix or send me that file, then re-run.")
        sys.exit(1)
    for path, text in cache.items():
        Path(path).write_text(text)
    print("\nAll patches written.")


if __name__ == "__main__":
    main()

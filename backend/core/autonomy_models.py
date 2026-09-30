"""
DB models for AI autonomy (PLAN.md §5.3, Phase 6).

Kept in their own module so backend/models.py does not need editing. They
register on the shared Base and are imported by backend.core.autonomy, which
main.py imports (via the autonomy route) BEFORE init_db() runs create_all() —
so both tables are created automatically on the next start. No migration
needed: these are new tables, not new columns on existing ones.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import Integer, Text, Boolean, DateTime, JSON, Index
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class AIAction(Base):
    """
    One row per autonomous (or suggested) change. This is the audit log the
    plan requires: what changed, why, when, and whether it can be undone.

    status:
      applied    - executed (by the AI gate, or by a human approving a suggestion)
      suggested  - AI review was not confident enough; waiting for a human
      vetoed     - the AI review rejected the proposal; nothing changed
      dismissed  - a human rejected a suggestion; nothing changed
      reverted   - an applied action was undone (see reverted_by: human/auto)
      expired    - a suggestion nobody answered within 24h; nothing changed
      failed     - the change could not be applied (bounds/state check failed)
    """
    __tablename__ = "ai_actions"

    id: Mapped[int] = mapped_column(primary_key=True)
    action_type: Mapped[str] = mapped_column(Text, nullable=False)   # wallet_pause | gas_multiplier | task_disable | project_priority
    target_type: Mapped[str] = mapped_column(Text, nullable=False)   # wallet | task | project
    target_id: Mapped[int] = mapped_column(Integer, nullable=False)
    chain_id: Mapped[Optional[int]] = mapped_column(Integer)
    project_id: Mapped[Optional[int]] = mapped_column(Integer)

    status: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    decided_by: Mapped[Optional[str]] = mapped_column(Text)          # ai | human

    summary: Mapped[str] = mapped_column(Text, nullable=False)       # one line, human readable
    reason: Mapped[str] = mapped_column(Text, nullable=False)        # the verified facts that triggered it
    ai_reasoning: Mapped[Optional[str]] = mapped_column(Text)        # what the AI reviewer said
    before_state: Mapped[Optional[dict]] = mapped_column(JSON)
    after_state: Mapped[Optional[dict]] = mapped_column(JSON)
    reversible: Mapped[bool] = mapped_column(Boolean, default=True)
    cause_category: Mapped[Optional[str]] = mapped_column(Text)      # failure category behind a wallet pause (drives auto-resume)

    validation_id: Mapped[Optional[int]] = mapped_column(Integer)    # AIValidation row for the review
    agreement_score: Mapped[Optional[int]] = mapped_column(Integer)
    error: Mapped[Optional[str]] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    applied_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    reverted_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    reverted_by: Mapped[Optional[str]] = mapped_column(Text)         # human | auto

    __table_args__ = (
        Index("ix_ai_actions_target", "target_type", "target_id", "created_at"),
    )


class AutonomyState(Base):
    """
    Single row (id=1) persisting the AI-autonomy freeze flag, so a crash or
    restart (systemd Restart=on-failure) can never silently re-enable autonomy
    after the operator froze it. Loaded into kill_switch at startup.
    """
    __tablename__ = "ai_autonomy_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    paused: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_by: Mapped[Optional[str]] = mapped_column(Text)

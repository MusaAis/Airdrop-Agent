from backend.database import Base
from datetime import datetime, date
from typing import Optional, List
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, JSON, ForeignKey,
    UniqueConstraint, Text, Date, text
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship



class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String, nullable=False)
    totp_secret: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class Chain(Base):
    __tablename__ = "chains"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    chain_id: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    rpc_urls: Mapped[dict] = mapped_column(JSON, nullable=False)
    explorer_url: Mapped[Optional[str]] = mapped_column(Text)
    gas_token_symbol: Mapped[str] = mapped_column(Text, nullable=False)
    gas_token_is_native: Mapped[bool] = mapped_column(Boolean, nullable=False)
    gas_token_contract: Mapped[Optional[str]] = mapped_column(Text)
    gas_token_decimals: Mapped[int] = mapped_column(Integer, nullable=False)
    gas_fee_model: Mapped[str] = mapped_column(Text, default="legacy")   # "legacy" or "eip1559"
    min_gas_balance_warning: Mapped[float] = mapped_column(Float, nullable=False)
    min_gas_balance_critical: Mapped[float] = mapped_column(Float, nullable=False)
    rpc_rate_limit_per_sec: Mapped[int] = mapped_column(Integer, default=10)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class ChainToken(Base):
    __tablename__ = "chain_tokens"
    id: Mapped[int] = mapped_column(primary_key=True)
    chain_id: Mapped[int] = mapped_column(ForeignKey("chains.id"), nullable=False)
    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    contract_address: Mapped[str] = mapped_column(Text, nullable=False)
    decimals: Mapped[int] = mapped_column(Integer, nullable=False)
    coingecko_id: Mapped[Optional[str]] = mapped_column(Text)
    is_gas_token: Mapped[bool] = mapped_column(Boolean, default=False)
    is_stable: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class Faucet(Base):
    __tablename__ = "faucets"
    id: Mapped[int] = mapped_column(primary_key=True)
    chain_id: Mapped[Optional[int]] = mapped_column(ForeignKey("chains.id"))
    project_id: Mapped[Optional[int]] = mapped_column(ForeignKey("projects.id"))
    name: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    fallback_urls: Mapped[dict] = mapped_column(JSON)
    method: Mapped[str] = mapped_column(Text, default="POST")
    body_template: Mapped[dict] = mapped_column(JSON)
    cooldown_hours: Mapped[int] = mapped_column(Integer, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class FaucetToken(Base):
    __tablename__ = "faucet_tokens"
    id: Mapped[int] = mapped_column(primary_key=True)
    faucet_id: Mapped[int] = mapped_column(ForeignKey("faucets.id"), nullable=False)
    token_symbol: Mapped[str] = mapped_column(Text, nullable=False)
    token_contract: Mapped[Optional[str]] = mapped_column(Text)
    amount_given: Mapped[float] = mapped_column(Float, nullable=False)
    decimals: Mapped[int] = mapped_column(Integer, nullable=False)

class FaucetRequest(Base):
    __tablename__ = "faucet_requests"
    id: Mapped[int] = mapped_column(primary_key=True)
    wallet_id: Mapped[int] = mapped_column(ForeignKey("wallets.id"), nullable=False)
    faucet_id: Mapped[int] = mapped_column(ForeignKey("faucets.id"), nullable=False)
    requested_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    tokens_received: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    trigger_type: Mapped[str] = mapped_column(Text)
    error_message: Mapped[Optional[str]] = mapped_column(Text)

class Proxy(Base):
    __tablename__ = "proxies"
    id: Mapped[int] = mapped_column(primary_key=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    wallet_id: Mapped[Optional[int]] = mapped_column(ForeignKey("wallets.id"))
    last_verified: Mapped[Optional[datetime]] = mapped_column(DateTime)
    ip_reputation_score: Mapped[Optional[int]] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class Wallet(Base):
    __tablename__ = "wallets"
    id: Mapped[int] = mapped_column(primary_key=True)
    address: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    is_hd: Mapped[bool] = mapped_column(Boolean, default=True)
    hd_index: Mapped[Optional[int]] = mapped_column(Integer)
    encrypted_private_key: Mapped[Optional[str]] = mapped_column(Text)
    name: Mapped[Optional[str]] = mapped_column(Text)
    tags: Mapped[dict] = mapped_column(JSON, default=[])
    proxy_id: Mapped[Optional[int]] = mapped_column(ForeignKey("proxies.id"))
    persona: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(Text, default="active")
    is_gas_wallet: Mapped[bool] = mapped_column(Boolean, default=False)
    failure_count: Mapped[int] = mapped_column(Integer, default=0)
    last_active: Mapped[Optional[datetime]] = mapped_column(DateTime)
    last_selected_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    warmup_complete: Mapped[bool] = mapped_column(Boolean, default=False)
    warmup_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    sybil_risk_score: Mapped[int] = mapped_column(Integer, default=0)
    health_score: Mapped[int] = mapped_column(Integer, default=100)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class WalletSettings(Base):
    __tablename__ = "wallet_settings"
    id: Mapped[int] = mapped_column(primary_key=True)
    wallet_id: Mapped[int] = mapped_column(ForeignKey("wallets.id"), unique=True, nullable=False)
    amount_min_override: Mapped[Optional[float]] = mapped_column(Float)
    amount_max_override: Mapped[Optional[float]] = mapped_column(Float)
    amount_distribution: Mapped[str] = mapped_column(Text, default="weighted_low")
    amount_vary_daily: Mapped[bool] = mapped_column(Boolean, default=True)
    active_hour_start: Mapped[Optional[int]] = mapped_column(Integer)
    active_hour_end: Mapped[Optional[int]] = mapped_column(Integer)
    start_offset_max_mins: Mapped[int] = mapped_column(Integer, default=45)
    sleep_min_mins: Mapped[int] = mapped_column(Integer, default=2)
    sleep_max_mins: Mapped[int] = mapped_column(Integer, default=8)
    gas_multiplier: Mapped[float] = mapped_column(Float, default=1.0)
    bidirectional_default: Mapped[bool] = mapped_column(Boolean, default=True)
    daily_tx_min: Mapped[int] = mapped_column(Integer, default=2)
    daily_tx_max: Mapped[int] = mapped_column(Integer, default=7)
    ai_validated: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class WalletBalance(Base):
    __tablename__ = "wallet_balances"
    id: Mapped[int] = mapped_column(primary_key=True)
    wallet_id: Mapped[int] = mapped_column(ForeignKey("wallets.id"), nullable=False)
    chain_id: Mapped[int] = mapped_column(ForeignKey("chains.id"), nullable=False)
    token_symbol: Mapped[str] = mapped_column(Text, nullable=False)
    balance: Mapped[float] = mapped_column(Float, nullable=False)
    usd_value: Mapped[float] = mapped_column(Float)
    last_updated: Mapped[datetime] = mapped_column(DateTime, nullable=False)

class WalletNonce(Base):
    __tablename__ = "wallet_nonces"
    id: Mapped[int] = mapped_column(primary_key=True)
    wallet_id: Mapped[int] = mapped_column(ForeignKey("wallets.id"), nullable=False)
    chain_id: Mapped[int] = mapped_column(ForeignKey("chains.id"), nullable=False)
    nonce: Mapped[int] = mapped_column(Integer, nullable=False)
    locked: Mapped[bool] = mapped_column(Boolean, default=False)
    locked_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    __table_args__ = (UniqueConstraint("wallet_id", "chain_id"),)

class ActiveTask(Base):
    __tablename__ = "active_tasks"
    id: Mapped[int] = mapped_column(primary_key=True)
    wallet_id: Mapped[int] = mapped_column(ForeignKey("wallets.id"), nullable=False)
    chain_id: Mapped[int] = mapped_column(Integer, nullable=False)
    task_config_id: Mapped[int] = mapped_column(ForeignKey("task_configs.id"), nullable=False)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    worker_slot: Mapped[int] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    timeout_at: Mapped[datetime] = mapped_column(DateTime)
    __table_args__ = (UniqueConstraint("wallet_id", "chain_id"),)

class Project(Base):
    __tablename__ = "projects"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    parent_project_id: Mapped[Optional[int]] = mapped_column(ForeignKey("projects.id"))
    chain_ids: Mapped[dict] = mapped_column(JSON)
    website: Mapped[Optional[str]] = mapped_column(Text)
    twitter: Mapped[Optional[str]] = mapped_column(Text)
    discord: Mapped[Optional[str]] = mapped_column(Text)
    # status values: active / paused / stopped / archived / monitor / dead
    #   - paused: temporary (project.pause) — circuit breaker also uses this
    #   - stopped: deliberate manual halt (Phase 4) — same lifecycle slot as
    #     paused/resume, just a distinct value so "I stopped this on purpose"
    #     is distinguishable from a circuit-breaker auto-pause in reports
    #   - archived: soft-delete (Phase 4) — hidden from the default project
    #     list but the row is never removed, so historical stats (Phase 7
    #     dashboard) can still count it
    status: Mapped[str] = mapped_column(Text, default="active")
    priority: Mapped[int] = mapped_column(Integer, default=5)
    max_concurrent_wallets: Mapped[int] = mapped_column(Integer, default=2)
    ai_confidence: Mapped[Optional[int]] = mapped_column(Integer)
    ai_last_verified: Mapped[Optional[datetime]] = mapped_column(DateTime)
    tge_date: Mapped[Optional[date]] = mapped_column(Date)
    airdrop_date: Mapped[Optional[date]] = mapped_column(Date)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    circuit_breaker_active: Mapped[bool] = mapped_column(Boolean, default=False)
    auto_claim_threshold_usd: Mapped[float] = mapped_column(Float, default=50.0)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # --- Phase 4: eligibility declaration (manual, website-only) ---
    # "pending" until declared eligible/not_eligible on the dashboard. Once
    # declared either way, queue_manager.py refuses to schedule any new task
    # for this project regardless of `status` — a declared project is done
    # farming, independent of whether status is still "active".
    eligibility_status: Mapped[str] = mapped_column(Text, default="pending")
    eligibility_value_usd: Mapped[Optional[float]] = mapped_column(Float)
    eligibility_declared_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    archived_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

class ProjectContract(Base):
    __tablename__ = "project_contracts"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    chain_id: Mapped[int] = mapped_column(ForeignKey("chains.id"), nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    address: Mapped[str] = mapped_column(Text, nullable=False)
    abi_fragment: Mapped[dict] = mapped_column(JSON)
    bytecode_hash: Mapped[Optional[str]] = mapped_column(Text)
    last_hash_check: Mapped[Optional[datetime]] = mapped_column(DateTime)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class ProjectCriteria(Base):
    __tablename__ = "project_criteria"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    type: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    threshold: Mapped[Optional[float]] = mapped_column(Float)
    unit: Mapped[Optional[str]] = mapped_column(Text)
    chain_id: Mapped[Optional[int]] = mapped_column(Integer)
    contract_address: Mapped[Optional[str]] = mapped_column(Text)
    source_quote: Mapped[Optional[str]] = mapped_column(Text)
    uncertain: Mapped[bool] = mapped_column(Boolean, default=False)
    ai_extracted: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class TaskConfig(Base):
    __tablename__ = "task_configs"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    task_type: Mapped[str] = mapped_column(Text, nullable=False)
    chain_id: Mapped[int] = mapped_column(ForeignKey("chains.id"), nullable=False)
    parameters: Mapped[dict] = mapped_column(JSON)
    dependency_task_ids: Mapped[dict] = mapped_column(JSON)
    frequency_mins: Mapped[int] = mapped_column(Integer, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    slippage_tolerance: Mapped[float] = mapped_column(Float, default=0.005)
    deadline_mins: Mapped[int] = mapped_column(Integer, default=20)
    min_amount: Mapped[float] = mapped_column(Float)
    max_amount: Mapped[float] = mapped_column(Float)
    amount_distribution: Mapped[str] = mapped_column(Text, default="weighted_low")
    amount_vary_daily: Mapped[bool] = mapped_column(Boolean, default=True)
    daily_tx_min: Mapped[int] = mapped_column(Integer, default=2)
    daily_tx_max: Mapped[int] = mapped_column(Integer, default=7)
    token_in: Mapped[Optional[str]] = mapped_column(Text)
    token_out: Mapped[Optional[str]] = mapped_column(Text)
    bidirectional: Mapped[bool] = mapped_column(Boolean, default=False)
    token_in_reverse: Mapped[Optional[str]] = mapped_column(Text)
    token_out_reverse: Mapped[Optional[str]] = mapped_column(Text)
    contract_label: Mapped[Optional[str]] = mapped_column(Text)
    ai_validated: Mapped[bool] = mapped_column(Boolean, default=False)
    ai_validation_id: Mapped[Optional[int]] = mapped_column(ForeignKey("ai_validations.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class TaskDailyProgress(Base):
    __tablename__ = "task_daily_progress"
    id: Mapped[int] = mapped_column(primary_key=True)
    wallet_id: Mapped[int] = mapped_column(ForeignKey("wallets.id"), nullable=False)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    task_config_id: Mapped[int] = mapped_column(ForeignKey("task_configs.id"), nullable=False)
    date: Mapped[str] = mapped_column(Text, nullable=False)
    daily_target: Mapped[int] = mapped_column(Integer, nullable=False)
    completed: Mapped[int] = mapped_column(Integer, default=0)
    __table_args__ = (UniqueConstraint("wallet_id", "project_id", "task_config_id", "date"),)

class TaskSchedule(Base):
    __tablename__ = "task_schedule"
    id: Mapped[int] = mapped_column(primary_key=True)
    wallet_id: Mapped[int] = mapped_column(ForeignKey("wallets.id"), nullable=False)
    task_config_id: Mapped[int] = mapped_column(ForeignKey("task_configs.id"), nullable=False)
    next_run_at: Mapped[datetime] = mapped_column(DateTime)
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    priority: Mapped[int] = mapped_column(Integer, default=5)

class Transaction(Base):
    __tablename__ = "transactions"
    id: Mapped[int] = mapped_column(primary_key=True)
    wallet_id: Mapped[int] = mapped_column(ForeignKey("wallets.id"), nullable=False)
    task_config_id: Mapped[int] = mapped_column(ForeignKey("task_configs.id"), nullable=False)
    chain_id: Mapped[int] = mapped_column(ForeignKey("chains.id"), nullable=False)
    tx_hash: Mapped[str] = mapped_column(Text, unique=True)
    status: Mapped[str] = mapped_column(Text)
    gas_used: Mapped[Optional[int]] = mapped_column(Integer)
    gas_price: Mapped[Optional[float]] = mapped_column(Float)
    gas_token: Mapped[Optional[str]] = mapped_column(Text)
    gas_cost_usd: Mapped[Optional[float]] = mapped_column(Float)
    block_number: Mapped[Optional[int]] = mapped_column(Integer)
    confirmations: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    is_approval: Mapped[bool] = mapped_column(Boolean, default=False)
    parent_tx_id: Mapped[Optional[int]] = mapped_column(ForeignKey("transactions.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

class TokenApproval(Base):
    __tablename__ = "token_approvals"
    id: Mapped[int] = mapped_column(primary_key=True)
    wallet_id: Mapped[int] = mapped_column(ForeignKey("wallets.id"), nullable=False)
    chain_id: Mapped[int] = mapped_column(ForeignKey("chains.id"), nullable=False)
    token_contract: Mapped[str] = mapped_column(Text, nullable=False)
    spender_contract: Mapped[str] = mapped_column(Text, nullable=False)
    approved_amount: Mapped[str] = mapped_column(Text, nullable=False)
    approved_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    tx_hash: Mapped[str] = mapped_column(Text, nullable=False)
    __table_args__ = (UniqueConstraint("wallet_id", "chain_id", "token_contract", "spender_contract"),)

class AIValidation(Base):
    __tablename__ = "ai_validations"
    id: Mapped[int] = mapped_column(primary_key=True)
    task_type: Mapped[str] = mapped_column(Text, nullable=False)
    input_hash: Mapped[str] = mapped_column(Text, nullable=False)
    groq_output: Mapped[dict] = mapped_column(JSON)
    gemini_output: Mapped[dict] = mapped_column(JSON)
    agreement_score: Mapped[int] = mapped_column(Integer, default=0)
    conflict_fields: Mapped[dict] = mapped_column(JSON)
    final_decision: Mapped[dict] = mapped_column(JSON)
    requires_human: Mapped[bool] = mapped_column(Boolean, default=False)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    human_decision: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class CompletedProjectsBlacklist(Base):
    __tablename__ = "completed_projects_blacklist"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_name: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    tge_date: Mapped[Optional[date]] = mapped_column(Date)
    airdrop_date: Mapped[Optional[date]] = mapped_column(Date)
    reason: Mapped[str] = mapped_column(Text)
    added_by: Mapped[str] = mapped_column(Text, default="ai")
    added_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(Text, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    wallet_id: Mapped[Optional[int]] = mapped_column(ForeignKey("wallets.id"))
    project_id: Mapped[Optional[int]] = mapped_column(ForeignKey("projects.id"))
    chain_id: Mapped[Optional[int]] = mapped_column(ForeignKey("chains.id"))
    sent_telegram: Mapped[bool] = mapped_column(Boolean, default=False)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class AgentStatus(Base):
    __tablename__ = "agent_status"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, server_default=text('1'))
    last_heartbeat: Mapped[Optional[datetime]] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(Text, default="stopped")
    current_tasks: Mapped[dict] = mapped_column(JSON)
    next_scheduled_tasks: Mapped[dict] = mapped_column(JSON)
    uptime_start: Mapped[Optional[datetime]] = mapped_column(DateTime)
    memory_pct: Mapped[Optional[float]] = mapped_column(Float)
    worker_slots_active: Mapped[int] = mapped_column(Integer, default=0)
    worker_slots_max: Mapped[int] = mapped_column(Integer, default=4)

class Log(Base):
    __tablename__ = "logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    wallet_id: Mapped[Optional[int]] = mapped_column(ForeignKey("wallets.id"))
    chain_id: Mapped[Optional[int]] = mapped_column(Integer)
    task_config_id: Mapped[Optional[int]] = mapped_column(Integer)
    project_id: Mapped[Optional[int]] = mapped_column(Integer)
    task_name: Mapped[Optional[str]] = mapped_column(Text)
    tx_hash: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    gas_used: Mapped[Optional[int]] = mapped_column(Integer)
    gas_cost_usd: Mapped[Optional[float]] = mapped_column(Float)
    is_dry_run: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class LogsArchive(Base):
    __tablename__ = "logs_archive"
    id: Mapped[int] = mapped_column(primary_key=True)
    wallet_id: Mapped[Optional[int]] = mapped_column(Integer)
    chain_id: Mapped[Optional[int]] = mapped_column(Integer)
    task_config_id: Mapped[Optional[int]] = mapped_column(Integer)
    project_id: Mapped[Optional[int]] = mapped_column(Integer)
    task_name: Mapped[Optional[str]] = mapped_column(Text)
    tx_hash: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    gas_used: Mapped[Optional[int]] = mapped_column(Integer)
    gas_cost_usd: Mapped[Optional[float]] = mapped_column(Float)
    is_dry_run: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class RPCLog(Base):
    __tablename__ = "rpc_request_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    chain_id: Mapped[int] = mapped_column(ForeignKey("chains.id"), nullable=False)
    rpc_url: Mapped[str] = mapped_column(Text, nullable=False)
    method: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class LoginAttempt(Base):
    __tablename__ = "login_attempts"
    id: Mapped[int] = mapped_column(primary_key=True)
    ip_address: Mapped[str] = mapped_column(Text, nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class AgentSecret(Base):
    __tablename__ = "agent_secrets"
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)  # encrypted mnemonic
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class CompetitorWallet(Base):
    __tablename__ = "competitor_wallets"
    id: Mapped[int] = mapped_column(primary_key=True)
    address: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    label: Mapped[Optional[str]] = mapped_column(Text)
    added_by: Mapped[str] = mapped_column(Text, default="manual")
    last_analyzed: Mapped[Optional[datetime]] = mapped_column(DateTime)
    transaction_patterns: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

# DiscoveryRun model removed — the discovery/scraping system it tracked was
# removed entirely (see PLAN.md §3). Projects are now submitted manually only.

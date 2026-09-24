import psutil
import logging
from backend.config import MEMORY_ALERT_THRESHOLD_PCT

logger = logging.getLogger("airdrop.memory")

# Configurable at runtime via /alert_memory
MEMORY_CRITICAL_PCT = MEMORY_ALERT_THRESHOLD_PCT


def check_memory() -> float:
    return psutil.virtual_memory().percent


def is_memory_critical() -> bool:
    pct = check_memory()
    if pct > MEMORY_CRITICAL_PCT:
        logger.warning(f"Memory critical: {pct}% > {MEMORY_CRITICAL_PCT}%")
        return True
    return False

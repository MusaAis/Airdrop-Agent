import random
import logging
from datetime import datetime, timezone
from typing import Optional
from backend.models import WalletSettings

logger = logging.getLogger("airdrop.behavior")


def weighted_random_amount(
    min_amount: float, max_amount: float, distribution: str = "weighted_low"
) -> float:
    """
    Weighted random amount within range.
      weighted_low:  60% lower third, 30% middle, 10% upper
      weighted_high: 10% lower, 30% middle, 60% upper
      uniform:       pure random
    """
    if min_amount >= max_amount:
        return min_amount

    r = random.random()
    span = max_amount - min_amount
    lower_end = min_amount + span * 0.33
    upper_start = min_amount + span * 0.67

    if distribution == "weighted_low":
        if r < 0.60:
            return round(random.uniform(min_amount, lower_end), 6)
        elif r < 0.90:
            return round(random.uniform(lower_end, upper_start), 6)
        else:
            return round(random.uniform(upper_start, max_amount), 6)

    elif distribution == "weighted_high":
        if r < 0.10:
            return round(random.uniform(min_amount, lower_end), 6)
        elif r < 0.40:
            return round(random.uniform(lower_end, upper_start), 6)
        else:
            return round(random.uniform(upper_start, max_amount), 6)

    else:  # uniform
        return round(random.uniform(min_amount, max_amount), 6)


def is_in_active_hours(settings: Optional[WalletSettings]) -> bool:
    """Return True if current UTC hour is within wallet's active window."""
    if not settings:
        return True
    if settings.active_hour_start is None or settings.active_hour_end is None:
        return True

    now_hour = datetime.now(timezone.utc).hour
    start = settings.active_hour_start
    end = settings.active_hour_end

    if start <= end:
        return start <= now_hour < end
    else:
        # Wraps midnight e.g. 22→06
        return now_hour >= start or now_hour < end


def should_flip_direction(bidirectional: bool) -> bool:
    """Randomly decide to run task in reverse direction."""
    return bidirectional and random.random() < 0.5


def get_sleep_seconds(settings: Optional[WalletSettings]) -> int:
    """Random sleep duration within wallet's configured range."""
    if not settings:
        return random.randint(120, 480)
    min_secs = (settings.sleep_min_mins or 2) * 60
    max_secs = (settings.sleep_max_mins or 8) * 60
    return random.randint(min_secs, max_secs)


def get_start_offset_seconds(settings: Optional[WalletSettings]) -> int:
    """Random start delay to stagger same-project wallet batches."""
    max_mins = settings.start_offset_max_mins if settings else 45
    return random.randint(0, max_mins * 60)


def apply_gas_multiplier(base_gas: int, settings: Optional[WalletSettings]) -> int:
    """Apply wallet's gas multiplier with ±5% variation to avoid identical gas prices."""
    multiplier = (settings.gas_multiplier if settings else 1.0) or 1.0
    variation = random.uniform(0.95, 1.05)
    return int(base_gas * multiplier * variation)

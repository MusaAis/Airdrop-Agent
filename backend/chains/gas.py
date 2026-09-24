"""
Gas price oracle with 6-hour rolling average and spike detection.
Stores sampled gas prices in memory with timestamps for proper averaging.
"""
import asyncio
import logging
from collections import deque
from datetime import datetime, timezone, timedelta
from typing import Deque, Tuple
from web3 import AsyncWeb3

logger = logging.getLogger("airdrop.gas")

# Per-chain history: chain_db_id -> deque of (timestamp, gas_price_wei)
_gas_history: dict[int, Deque[Tuple[datetime, int]]] = {}
_HISTORY_WINDOW_HOURS = 6
_MAX_SAMPLES = 72  # 6 hours × 12 samples/hour (every 5 min)


def _get_history(chain_db_id: int) -> Deque:
    if chain_db_id not in _gas_history:
        _gas_history[chain_db_id] = deque(maxlen=_MAX_SAMPLES)
    return _gas_history[chain_db_id]


async def get_current_gas_price(w3: AsyncWeb3) -> int:
    """Return current gas price in wei."""
    return await w3.eth.gas_price


async def sample_gas_price(chain_db_id: int, w3: AsyncWeb3) -> int:
    """Sample and store current gas price. Call every 5-10 minutes via scheduler."""
    try:
        price = await get_current_gas_price(w3)
        history = _get_history(chain_db_id)
        now = datetime.now(timezone.utc)
        history.append((now, price))
        logger.debug(f"Gas sample chain={chain_db_id}: {price} wei")
        return price
    except Exception as e:
        logger.error(f"Gas sample error chain={chain_db_id}: {e}")
        return 0


async def get_6h_average_gas(chain_db_id: int, w3: AsyncWeb3) -> float:
    """
    Return 6-hour average gas price.
    If no history yet, sample now and return current as baseline.
    """
    history = _get_history(chain_db_id)

    if not history:
        # Cold start: sample now as baseline
        price = await sample_gas_price(chain_db_id, w3)
        return float(price)

    cutoff = datetime.now(timezone.utc) - timedelta(hours=_HISTORY_WINDOW_HOURS)
    recent = [p for ts, p in history if ts >= cutoff]

    if not recent:
        # All samples too old — use most recent
        recent = [history[-1][1]]

    return sum(recent) / len(recent)


def is_gas_spike(current: int, average: float, multiplier: float = 3.0) -> bool:
    """Return True if current gas price exceeds average × multiplier."""
    if average <= 0:
        return False
    return current > average * multiplier


async def get_gas_spike_status(chain_db_id: int, w3: AsyncWeb3, multiplier: float = 3.0) -> dict:
    """Full spike status report for a chain."""
    current = await get_current_gas_price(w3)
    average = await get_6h_average_gas(chain_db_id, w3)
    spike = is_gas_spike(current, average, multiplier)
    ratio = round(current / average, 2) if average > 0 else 0
    return {
        "chain_db_id": chain_db_id,
        "current_gwei": round(current / 1e9, 4),
        "average_6h_gwei": round(average / 1e9, 4),
        "ratio": ratio,
        "threshold_multiplier": multiplier,
        "is_spike": spike,
        "samples_in_window": len([p for ts, p in _get_history(chain_db_id)
                                   if ts >= datetime.now(timezone.utc) - timedelta(hours=6)]),
    }


async def get_optimal_gas_windows(chain_db_id: int) -> list:
    """
    Analyze historical gas samples to identify lowest-gas time windows.
    Groups samples by UTC hour and returns sorted by average price.
    """
    history = _get_history(chain_db_id)
    if len(history) < 12:
        return [{"message": "Not enough history yet — need at least 1 hour of samples"}]

    from collections import defaultdict
    hour_buckets: dict[int, list] = defaultdict(list)
    for ts, price in history:
        hour_buckets[ts.hour].append(price)

    hour_avgs = []
    for hour, prices in hour_buckets.items():
        avg = sum(prices) / len(prices)
        hour_avgs.append({
            "hour_utc": hour,
            "avg_gwei": round(avg / 1e9, 4),
            "samples": len(prices),
        })

    return sorted(hour_avgs, key=lambda x: x["avg_gwei"])[:8]


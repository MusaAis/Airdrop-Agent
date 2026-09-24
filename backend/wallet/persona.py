import random
from typing import Dict

def assign_default_persona() -> Dict:
    """Generate a random persona for a new wallet."""
    sleep_min = random.randint(2, 5)
    sleep_max = sleep_min + random.randint(2, 5)
    return {
        "sleep_min_mins": sleep_min,
        "sleep_max_mins": sleep_max,
        "gas_multiplier": round(random.uniform(0.9, 1.2), 2),
        "active_hour_start": random.randint(0, 8),   # early morning
        "active_hour_end": random.randint(14, 23),    # afternoon/evening
        "amount_distribution": random.choice(["weighted_low", "uniform", "weighted_high"]),
        "start_offset_max_mins": random.randint(20, 60),
        "bidirectional_default": random.choice([True, False]),
        "daily_tx_min": random.randint(1, 3),
        "daily_tx_max": random.randint(4, 8),
    }

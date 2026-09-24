"""
AI Key Pool — round-robin across multiple API keys per provider.

Configure extra keys in .env:
  GROQ_API_KEYS=key1,key2,key3        (comma-separated, no spaces)
  GEMINI_API_KEYS=key1,key2,key3

If only the single-key vars (GROQ_API_KEY / GEMINI_API_KEY) are set,
the pool just has one key and behaves identically to before.

On 429, the pool marks that key as cooled-down for COOLDOWN_SECS
and automatically picks the next available key.  If ALL keys are
cooling down it waits for the soonest one to recover.
"""

import asyncio
import logging
import os
import time
from typing import List, Optional

logger = logging.getLogger("airdrop.ai.key_pool")

COOLDOWN_SECS = 65  # one full minute + buffer before retrying a 429'd key


class KeyPool:
    """Thread-safe async key pool with per-key 429 cooldown tracking."""

    def __init__(self, keys: List[str], provider: str):
        self._keys = [k.strip() for k in keys if k.strip()]
        self._provider = provider
        # {key: cooldown_until_monotonic}
        self._cooling: dict[str, float] = {}
        self._idx = 0
        self._lock = asyncio.Lock()

    def _available(self) -> List[str]:
        now = time.monotonic()
        return [k for k in self._keys if self._cooling.get(k, 0) <= now]

    async def get(self) -> str:
        """Return the next available key, waiting if all are cooling."""
        async with self._lock:
            if not self._keys:
                raise RuntimeError(f"No {self._provider} API keys configured")

            for _ in range(len(self._keys)):
                k = self._keys[self._idx % len(self._keys)]
                self._idx += 1
                if self._cooling.get(k, 0) <= time.monotonic():
                    return k

            # All keys cooling — wait for the soonest recovery
            soonest = min(self._cooling.get(k, 0) for k in self._keys)
            wait = max(0.0, soonest - time.monotonic()) + 0.5
            logger.warning(
                "%s: all %d keys cooling down, waiting %.1fs",
                self._provider, len(self._keys), wait,
            )

        await asyncio.sleep(wait)

        async with self._lock:
            for k in self._keys:
                if self._cooling.get(k, 0) <= time.monotonic():
                    return k
            return self._keys[0]  # fallback

    async def mark_429(self, key: str):
        """Put a key in cooldown after receiving a 429."""
        async with self._lock:
            until = time.monotonic() + COOLDOWN_SECS
            self._cooling[key] = until
            avail = len(self._available())
            logger.warning(
                "%s key ...%s rate-limited, cooling %ds (%d/%d keys still available)",
                self._provider, key[-6:], COOLDOWN_SECS, avail, len(self._keys),
            )

    @property
    def count(self) -> int:
        return len(self._keys)


def _load_keys(multi_env: str, single_env: str) -> List[str]:
    """Load from PROVIDER_API_KEYS (comma-sep) or fall back to PROVIDER_API_KEY."""
    multi = os.getenv(multi_env, "")
    if multi.strip():
        keys = [k.strip() for k in multi.split(",") if k.strip()]
        if keys:
            return keys
    single = os.getenv(single_env, "")
    return [single] if single.strip() else []


# Module-level singletons — imported by groq_client and gemini_client
groq_pool  = KeyPool(_load_keys("GROQ_API_KEYS",   "GROQ_API_KEY"),   "Groq")
gemini_pool = KeyPool(_load_keys("GEMINI_API_KEYS", "GEMINI_API_KEY"), "Gemini")

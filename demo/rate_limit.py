"""In-memory IP rate limiter for the public demo.

The demo is intentionally unauthenticated, which makes it easy to share but
also easy to abuse — every request hits Gemini + Voyage, both of which cost
money. This module tracks request timestamps per client IP (sliding windows)
plus a global cap, and short-circuits requests that exceed either.

State is module-level so it survives Streamlit script reruns within the same
Python process. It does NOT survive a container restart — that's acceptable
for a demo and avoids needing Redis just for this.
"""
from __future__ import annotations

import os
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


# Per-IP sliding windows. Tunable via env so deploys can tighten/loosen
# without code changes.
PER_IP_PER_MINUTE = _env_int("DEMO_RATE_PER_MIN", 8)
PER_IP_PER_HOUR = _env_int("DEMO_RATE_PER_HOUR", 40)

# Global cap across all IPs — protects the Gemini / Voyage bill when a single
# IP rotates through a proxy pool.
GLOBAL_PER_HOUR = _env_int("DEMO_RATE_GLOBAL_PER_HOUR", 300)

WINDOWS_PER_IP: tuple[tuple[int, int], ...] = (
    (60, PER_IP_PER_MINUTE),
    (3600, PER_IP_PER_HOUR),
)
GLOBAL_WINDOW = 3600


@dataclass
class Decision:
    allowed: bool
    reason: str = ""
    retry_after_s: int = 0
    remaining_minute: int = 0
    remaining_hour: int = 0


_lock = threading.Lock()
_per_ip: dict[str, deque[float]] = defaultdict(deque)
_global: deque[float] = deque()


def _prune(q: deque[float], cutoff: float) -> None:
    while q and q[0] < cutoff:
        q.popleft()


def check(ip: str) -> Decision:
    """Atomically check + record a request from `ip`.

    On allow: the timestamp is appended to the relevant queues so a follow-up
    call from the same IP sees it. On deny: nothing is recorded.
    """
    now = time.time()
    with _lock:
        q = _per_ip[ip]
        _prune(q, now - max(w for w, _ in WINDOWS_PER_IP))
        _prune(_global, now - GLOBAL_WINDOW)

        # Per-IP windows
        for window, limit in WINDOWS_PER_IP:
            recent = sum(1 for t in q if t >= now - window)
            if recent >= limit:
                # Earliest timestamp in window dictates retry-after.
                first_in_window = next((t for t in q if t >= now - window), now)
                wait = int(first_in_window + window - now) + 1
                return Decision(
                    allowed=False,
                    reason=(
                        f"Превышен лимит: {limit} запросов в {window // 60} мин "
                        f"с одного IP."
                    ),
                    retry_after_s=max(wait, 1),
                )

        # Global cap
        if len(_global) >= GLOBAL_PER_HOUR:
            first = _global[0]
            wait = int(first + GLOBAL_WINDOW - now) + 1
            return Decision(
                allowed=False,
                reason=(
                    f"Сервис принимает не более {GLOBAL_PER_HOUR} запросов в час "
                    f"суммарно. Попробуй позже."
                ),
                retry_after_s=max(wait, 1),
            )

        q.append(now)
        _global.append(now)

        remaining_minute = PER_IP_PER_MINUTE - sum(
            1 for t in q if t >= now - 60
        )
        remaining_hour = PER_IP_PER_HOUR - sum(
            1 for t in q if t >= now - 3600
        )

    return Decision(
        allowed=True,
        remaining_minute=max(remaining_minute, 0),
        remaining_hour=max(remaining_hour, 0),
    )


def snapshot(ip: str) -> tuple[int, int]:
    """Read-only counts of remaining requests for `ip` without recording."""
    now = time.time()
    with _lock:
        q = _per_ip.get(ip)
        if q is None:
            return PER_IP_PER_MINUTE, PER_IP_PER_HOUR
        _prune(q, now - max(w for w, _ in WINDOWS_PER_IP))
        used_min = sum(1 for t in q if t >= now - 60)
        used_hour = sum(1 for t in q if t >= now - 3600)
    return (
        max(PER_IP_PER_MINUTE - used_min, 0),
        max(PER_IP_PER_HOUR - used_hour, 0),
    )

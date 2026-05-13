"""In-memory IP rate limiter for the public demo.

The demo is intentionally unauthenticated, which makes it easy to share but
also easy to abuse — every request hits Gemini + Voyage, both of which cost
money. This module tracks request timestamps per client IP (sliding windows)
plus a global cap, and short-circuits requests that exceed either.

Defaults are tuned to stay strictly inside the free tiers:
- Voyage free tier: 3 RPM (query embedding bottleneck)
- Gemini AI Studio free tier: 10 RPM, 250 RPD

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
# without code changes. Defaults stay inside Voyage (3 RPM) + Gemini free tier.
PER_IP_PER_MINUTE = _env_int("DEMO_RATE_PER_MIN", 3)
PER_IP_PER_HOUR = _env_int("DEMO_RATE_PER_HOUR", 20)
PER_IP_PER_DAY = _env_int("DEMO_RATE_PER_DAY", 50)

# Global caps across all IPs — protect the Gemini / Voyage bill when a single
# attacker rotates through a proxy pool. Daily cap is the hard ceiling that
# keeps the whole service inside Gemini's 250 RPD free tier with margin.
GLOBAL_PER_HOUR = _env_int("DEMO_RATE_GLOBAL_PER_HOUR", 60)
GLOBAL_PER_DAY = _env_int("DEMO_RATE_GLOBAL_PER_DAY", 200)

WINDOWS_PER_IP: tuple[tuple[int, int], ...] = (
    (60, PER_IP_PER_MINUTE),
    (3600, PER_IP_PER_HOUR),
    (86400, PER_IP_PER_DAY),
)
WINDOWS_GLOBAL: tuple[tuple[int, int], ...] = (
    (3600, GLOBAL_PER_HOUR),
    (86400, GLOBAL_PER_DAY),
)


@dataclass
class Decision:
    allowed: bool
    reason: str = ""
    retry_after_s: int = 0
    remaining_minute: int = 0
    remaining_hour: int = 0
    remaining_day: int = 0


_lock = threading.Lock()
_per_ip: dict[str, deque[float]] = defaultdict(deque)
_global: deque[float] = deque()


def _prune(q: deque[float], cutoff: float) -> None:
    while q and q[0] < cutoff:
        q.popleft()


def _format_window(window_s: int) -> str:
    if window_s >= 86400:
        return f"{window_s // 86400} сут"
    if window_s >= 3600:
        return f"{window_s // 3600} час"
    return f"{window_s // 60} мин"


def check(ip: str) -> Decision:
    """Atomically check + record a request from `ip`.

    On allow: the timestamp is appended to the relevant queues so a follow-up
    call from the same IP sees it. On deny: nothing is recorded.
    """
    now = time.time()
    longest_per_ip = max(w for w, _ in WINDOWS_PER_IP)
    longest_global = max(w for w, _ in WINDOWS_GLOBAL)
    with _lock:
        q = _per_ip[ip]
        _prune(q, now - longest_per_ip)
        _prune(_global, now - longest_global)

        # Per-IP windows
        for window, limit in WINDOWS_PER_IP:
            recent = sum(1 for t in q if t >= now - window)
            if recent >= limit:
                first_in_window = next((t for t in q if t >= now - window), now)
                wait = int(first_in_window + window - now) + 1
                return Decision(
                    allowed=False,
                    reason=(
                        f"Превышен лимит: {limit} запросов в {_format_window(window)} "
                        f"с одного IP."
                    ),
                    retry_after_s=max(wait, 1),
                )

        # Global caps
        for window, limit in WINDOWS_GLOBAL:
            recent = sum(1 for t in _global if t >= now - window)
            if recent >= limit:
                first_in_window = next((t for t in _global if t >= now - window), now)
                wait = int(first_in_window + window - now) + 1
                return Decision(
                    allowed=False,
                    reason=(
                        f"Сервис принимает не более {limit} запросов в "
                        f"{_format_window(window)} суммарно. Попробуй позже."
                    ),
                    retry_after_s=max(wait, 1),
                )

        q.append(now)
        _global.append(now)

        rm_min = PER_IP_PER_MINUTE - sum(1 for t in q if t >= now - 60)
        rm_hour = PER_IP_PER_HOUR - sum(1 for t in q if t >= now - 3600)
        rm_day = PER_IP_PER_DAY - sum(1 for t in q if t >= now - 86400)

    return Decision(
        allowed=True,
        remaining_minute=max(rm_min, 0),
        remaining_hour=max(rm_hour, 0),
        remaining_day=max(rm_day, 0),
    )


def snapshot(ip: str) -> tuple[int, int, int]:
    """Read-only (remaining_min, remaining_hour, remaining_day) for `ip`."""
    now = time.time()
    with _lock:
        q = _per_ip.get(ip)
        if q is None:
            return PER_IP_PER_MINUTE, PER_IP_PER_HOUR, PER_IP_PER_DAY
        _prune(q, now - max(w for w, _ in WINDOWS_PER_IP))
        used_min = sum(1 for t in q if t >= now - 60)
        used_hour = sum(1 for t in q if t >= now - 3600)
        used_day = sum(1 for t in q if t >= now - 86400)
    return (
        max(PER_IP_PER_MINUTE - used_min, 0),
        max(PER_IP_PER_HOUR - used_hour, 0),
        max(PER_IP_PER_DAY - used_day, 0),
    )

"""Retrieval evaluation harness for personal-meeting-brain.

Loads `evals/queries.jsonl` and, for each query, runs `search()` end-to-end
(Voyage query embedding + sqlite-vec ANN). Records Recall@5, MRR@10, and two
latency series:

  * **e2e** — full search() call including Voyage round-trip (the user-facing
    number). Sampled from the *first* timed run per query, when the query
    embedding still needs to be fetched.
  * **search-only** — sqlite-vec MATCH + JOIN, with the query embedding
    served from a local disk cache. Sampled from the remaining repeats.

Query embeddings are cached at `evals/_query_embed_cache.json` so successive
runs (or a Voyage free-tier 3 RPM rate-limit) don't break reproducibility.

Usage:
    uv run python evals/run_evals.py
    uv run python evals/run_evals.py --repeats 5 --no-cache
"""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
import time
from pathlib import Path

from meeting_brain import embeddings
from meeting_brain.config import PROJECT_ROOT
from meeting_brain.db import connect
from meeting_brain.search import search

RECALL_AT = 5
MRR_AT = 10

_CACHE_PATH_DEFAULT = Path(__file__).resolve().parent / "_query_embed_cache.json"


def _normalize_path(p: str) -> str:
    return str((PROJECT_ROOT / p).resolve())


def _load_queries(path: Path) -> list[dict]:
    queries: list[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for i, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                raise SystemExit(f"queries.jsonl: line {i} is not valid JSON: {exc}")
            if "query" not in obj or "expected_paths" not in obj:
                raise SystemExit(f"queries.jsonl: line {i} missing required fields")
            obj["_expected_abs"] = {_normalize_path(p) for p in obj["expected_paths"]}
            queries.append(obj)
    if not queries:
        raise SystemExit(f"queries.jsonl is empty: {path}")
    return queries


def _recall_at_k(hits_paths: list[str], expected: set[str], k: int) -> int:
    return 1 if any(p in expected for p in hits_paths[:k]) else 0


def _mrr_at_k(hits_paths: list[str], expected: set[str], k: int) -> float:
    for rank, p in enumerate(hits_paths[:k], start=1):
        if p in expected:
            return 1.0 / rank
    return 0.0


def _percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    s = sorted(values)
    pos = (len(s) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(s) - 1)
    frac = pos - lo
    return s[lo] * (1 - frac) + s[hi] * frac


def _install_cache(cache_path: Path) -> dict:
    """Monkey-patch embeddings.embed_query to read/write a disk cache.

    Cache key is the SHA-256 of the query text (model + input_type are
    fixed for this project, so the text alone is a safe key). Returns the
    in-memory cache dict so callers can introspect hit/miss stats.
    """
    cache: dict[str, list[float]] = {}
    if cache_path.exists():
        try:
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print(f"warn: cache at {cache_path} is corrupt, ignoring", file=sys.stderr)
            cache = {}

    stats = {"hits": 0, "misses": 0}
    cache["__stats__"] = stats  # type: ignore[assignment]
    real_embed_query = embeddings.embed_query

    def cached_embed_query(text: str) -> list[float]:
        key = hashlib.sha256(text.encode("utf-8")).hexdigest()
        vec = cache.get(key)
        if vec is not None:
            stats["hits"] += 1
            return vec  # type: ignore[return-value]
        stats["misses"] += 1
        vec = real_embed_query(text)
        cache[key] = vec
        # Persist after every miss so a rate-limit interruption keeps progress.
        to_dump = {k: v for k, v in cache.items() if k != "__stats__"}
        cache_path.write_text(json.dumps(to_dump), encoding="utf-8")
        return vec

    embeddings.embed_query = cached_embed_query  # type: ignore[assignment]
    return cache


def main() -> int:
    parser = argparse.ArgumentParser(description="Run retrieval evals.")
    parser.add_argument("--queries", type=Path, default=Path(__file__).resolve().parent / "queries.jsonl")
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--repeats", type=int, default=3,
                        help="Timed runs per query. First run measures e2e (with Voyage); the rest measure search-only (cache hits).")
    parser.add_argument("--cache-path", type=Path, default=_CACHE_PATH_DEFAULT)
    parser.add_argument("--no-cache", action="store_true", help="Disable disk caching of query embeddings.")
    args = parser.parse_args()

    if not args.no_cache:
        cache = _install_cache(args.cache_path)
        print(f"Using query-embedding cache at {args.cache_path} "
              f"({len(cache) - 1} entries preloaded)", file=sys.stderr)

    queries = _load_queries(args.queries)
    print(f"Loaded {len(queries)} queries from {args.queries}", file=sys.stderr)

    conn = connect()
    e2e_latencies: list[float] = []          # first repeat per query (cold or cache-warm)
    search_only_latencies: list[float] = []  # remaining repeats per query
    recalls: list[int] = []
    mrrs: list[float] = []
    first_run_was_cold: list[bool] = []

    try:
        for idx, q in enumerate(queries, start=1):
            qtext = q["query"]
            expected = q["_expected_abs"]

            timings_ms: list[float] = []
            last_hits = None
            cache_before = None
            if not args.no_cache:
                cache_before = cache["__stats__"]["misses"]

            for r in range(args.repeats):
                t0 = time.perf_counter()
                hits = search(conn, qtext, top_k=args.top_k)
                t1 = time.perf_counter()
                timings_ms.append((t1 - t0) * 1000.0)
                last_hits = hits

            cold = False
            if not args.no_cache and cache_before is not None:
                cold = cache["__stats__"]["misses"] > cache_before
            first_run_was_cold.append(cold)

            assert last_hits is not None
            hits_paths = [h.source_path for h in last_hits]
            recall = _recall_at_k(hits_paths, expected, RECALL_AT)
            mrr = _mrr_at_k(hits_paths, expected, MRR_AT)
            recalls.append(recall)
            mrrs.append(mrr)

            e2e_latencies.append(timings_ms[0])
            if len(timings_ms) > 1:
                search_only_latencies.extend(timings_ms[1:])

            status = "HIT" if recall else "MISS"
            cold_tag = "cold" if cold else "warm"
            print(
                f"[{idx:02d}/{len(queries):02d}] {status:4s}  R@5={recall}  MRR@10={mrr:.3f}  "
                f"first={timings_ms[0]:.0f}ms ({cold_tag})  "
                f"rest_med={statistics.median(timings_ms[1:]) if len(timings_ms) > 1 else float('nan'):.1f}ms  "
                f"q={qtext[:60]}",
                file=sys.stderr,
            )

    finally:
        conn.close()

    recall_at_5 = sum(recalls) / len(recalls)
    mrr_at_10 = sum(mrrs) / len(mrrs)

    # Split e2e latencies by cold/warm so we can report a clean "with Voyage round-trip" number.
    cold_e2e = [lat for lat, c in zip(e2e_latencies, first_run_was_cold) if c]
    warm_e2e = [lat for lat, c in zip(e2e_latencies, first_run_was_cold) if not c]

    print()
    print("=" * 64)
    print("AGGREGATE RESULTS")
    print("=" * 64)
    print(f"Queries:                {len(queries)}")
    print(f"Repeats/query:          {args.repeats}")
    print(f"Recall@5:               {recall_at_5:.3f}  ({sum(recalls)}/{len(recalls)} hits)")
    print(f"MRR@10:                 {mrr_at_10:.3f}")
    print()
    print("Latency — end-to-end (search + Voyage query embed):")
    if cold_e2e:
        print(f"  cold (n={len(cold_e2e):>2d})  P50={_percentile(cold_e2e, 0.5):.0f} ms   "
              f"P95={_percentile(cold_e2e, 0.95):.0f} ms   "
              f"min={min(cold_e2e):.0f}   max={max(cold_e2e):.0f}")
    if warm_e2e:
        print(f"  warm (n={len(warm_e2e):>2d})  P50={_percentile(warm_e2e, 0.5):.0f} ms   "
              f"P95={_percentile(warm_e2e, 0.95):.0f} ms   "
              f"min={min(warm_e2e):.0f}   max={max(warm_e2e):.0f}")
    print()
    if search_only_latencies:
        print(f"Latency — search-only (sqlite-vec MATCH + JOIN, embedding from cache):")
        print(f"  n={len(search_only_latencies):>2d}  "
              f"P50={_percentile(search_only_latencies, 0.5):.2f} ms   "
              f"P95={_percentile(search_only_latencies, 0.95):.2f} ms   "
              f"min={min(search_only_latencies):.2f}   max={max(search_only_latencies):.2f}")
    print("=" * 64)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

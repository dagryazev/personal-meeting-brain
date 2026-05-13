# Architecture Review — Event Store Migration

**Date:** 2026-05-13
**Topic:** Migrating events out of PostgreSQL into a dedicated event store
**Attendees:** Anya, Lyosha, Denis

---

**Anya:** Today is the final review before I file the RFC with the team. After the May 1 incident it's clear: events shouldn't live in our main DB. We keep transactional customer data and the analytical event stream in the same place — they have different load patterns.

**Lyosha:** Agreed. Which options did you consider?

**Anya:** Three. First — ClickHouse, second — TimescaleDB, third — keep PostgreSQL but on a separate instance with aggressive time partitioning.

**Denis:** Criteria?

**Anya:**
1. Write throughput. Peak today is ~2000 events/sec, end-of-year target 5000.
2. Analytical query speed. Today "events for customer X for a month" takes 8–12 seconds.
3. Operational complexity. The less new stack, the better.
4. Infra cost.

**Lyosha:** Walk us through each.

**Anya:** ClickHouse — wins on analytical speed by 50–100x, wins on writes by 5–10x. Loses on operational complexity: new engine, new backup process, learning curve. TimescaleDB is a PostgreSQL extension, operationally almost free, analytics 5–10x faster, writes close to vanilla PG. Third option (separate PG) — simplest but doesn't fix the long-term problem.

**Denis:** Your pick?

**Anya:** TimescaleDB. Operationally we're not ready for ClickHouse — no specialist, Lyosha is the only devops. Headroom on Timescale is ~1.5 years of growth, which is enough.

**Lyosha:** Concur. I know PG operations; the extension shouldn't surprise me.

**Denis:** How long is the migration?

**Anya:** Clean proof-of-concept — two weeks. Full migration with traffic switchover and staged dual-write — two months, I'd budget three. That's no-surprises pace.

**Lyosha:** Regression risk?

**Anya:** Low, if we do dual-write right. Plan: new events write to PG and Timescale in parallel; we reconcile counts for a month. Once we're sure, flip reads to Timescale; one more month, then disable PG writes.

**Denis:** Trade-offs of TimescaleDB?

**Anya:** Downsides: vendor lock — it's a commercial product, the free self-hosted has limits. Continuous aggregates require rethinking some queries. And — some JOINs between Timescale tables and regular PG tables can be slow if the data lives on different instances.

**Lyosha:** On the same instance, JOINs work fine. Important — let's colocate Timescale next to the main DB initially, no separate instance.

**Anya:** Agreed. That simplifies phase one.

**Denis:** Budget?

**Anya:** Extra load on the instance — +30% RAM/disk. About €80/month at the current plan.

**Denis:** Approved. Write the RFC, on Monday we discuss with the team, then a migration plan for the next two sprints.

**Anya:** Done.

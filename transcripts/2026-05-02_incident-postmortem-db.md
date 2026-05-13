# Incident Postmortem — Production DB Outage

**Date:** 2026-05-02
**Incident:** INC-2026-0058
**Duration:** 47 minutes (01:14 — 02:01 UTC, 2026-05-01)
**Postmortem attendees:** Lyosha (incident commander), Anya, Denis, Mark

---

## Summary

During the night of April 30 to May 1, the production PostgreSQL instance became unavailable with "no space left on device". The API returned 503 for all write operations; reads degraded because the cache couldn't refresh. All customers in EU and US-East regions were affected. Recovery: raise the disk size via the provider console and force-VACUUM FULL on two tables.

## Timeline (UTC)

- **00:58** — internal alert "disk_usage > 92%" fired into the Slack #ops channel. No one reacted at night.
- **01:14** — first customer alert via status page: writes returning 503.
- **01:16** — PagerDuty escalated to Lyosha.
- **01:24** — Lyosha confirms diagnosis: disk full. Decides to grow the disk rather than emergency-VACUUM (which needs free space).
- **01:31** — disk grown from 500 GB to 1 TB. PostgreSQL does not auto-recover — the process hangs on recovery.
- **01:42** — Lyosha restarts the instance. Recovery takes 11 minutes.
- **01:53** — DB available but queries are slow. We run VACUUM FULL on the two largest tables.
- **02:01** — performance returns to normal, incident closed.

## What went well

- PagerDuty fired.
- Lyosha decided on the disk path within 10 minutes — not the fastest, but no panic.
- PostgreSQL recovery completed with no data loss.
- The customer status page updated automatically via the health check.

## What went badly

- **Alert went to the wrong channel.** "disk_usage > 92%" pages into #ops which is unwatched at night. It should have paged immediately.
- **The disk growth was foreseen.** Anya flagged DB growth in the Sprint 3 retro (2026-04-25). The plan was to research in sprint 4. The incident happened before the plan.
- **VACUUM FULL cost an extra 8 minutes.** We could have run parallel-vacuum, but under pressure no one remembered the syntax.

## Root cause

Technically — disk exhaustion driven by fast growth of the `events` table. Systemically — we knew about the problem but scheduled the work too late. Capacity planning wasn't automated: a 40 GB/quarter growth was noticed only in retro.

## Action items

1. **[Lyosha, by 2026-05-04]** Reroute the "disk_usage > 85%" alert from #ops to PagerDuty.
2. **[Anya + Lyosha, by 2026-05-08]** Archive events older than 90 days to S3 cold storage. Do not wait for sprint boundary.
3. **[Lyosha, by 2026-05-15]** Add a monthly capacity review with a 90-day forecast for disk, RAM, CPU.
4. **[Anya, by 2026-05-12]** Prepare an emergency-VACUUM runbook with ready-to-run commands.
5. **[Denis, by 2026-05-06]** Send affected customers a short retro-report via the support channel. Not an apology — a description plus what changes.

## Additional notes

No SLA financial credits owed — we stay within the 99.5% monthly budget (47 minutes fits), but barely. Next month we need to be extra careful.

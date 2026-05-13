# Daily Standup

**Date:** 2026-04-14
**Attendees:** Denis, Anya, Mark, Lyosha

---

**Denis:** Let's go. Anya, you're first.

**Anya:** Yesterday I finished the Redis Streams instrumentation — metrics are flowing into Grafana, the "queues-overview" dashboard is live. Interesting find: peak load is not in the evening as we thought, but at 11am — that lines up with the automatic warehouse sync from two of our largest customers. Today I'm starting the data-archival research.

**Denis:** Okay. Post the dashboard link in Slack so everyone can watch.

**Anya:** Will do.

**Mark:** I'm finishing wizard step 1 — welcome + industry select. Today I move on to step 2, import. And the Safari fix in parallel — it's quick, hopefully.

**Denis:** Any blockers?

**Mark:** One: on touch devices the progress bar jitters at the pixel level — a Safari quirk. It's polish, not a blocker.

**Lyosha:** I fixed yesterday's false-positive 4am alert — the threshold was set in bytes instead of megabytes, so it tripped every day. Apologies to oncall. Today: log-retention tuning. We're accumulating 200 GB a week in Loki, that's a lot.

**Denis:** Thanks. On me — two prospect demos at 14:00 and 16:00. If anyone hears me cursing in the office, it's not at you.

**Anya:** I have a blocker. I can't get read-only access to the prod DB for the archival research. Lyosha, can you help?

**Lyosha:** I'll spin up a read-replica with restricted permissions today. Should take a couple of hours.

**Denis:** Got it. Until tomorrow.

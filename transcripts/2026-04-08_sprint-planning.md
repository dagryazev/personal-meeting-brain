# Sprint Planning — Q2 Sprint 3

**Date:** 2026-04-08
**Attendees:** Denis (PM), Anya (Backend), Mark (Frontend), Sonya (Design), Lyosha (DevOps)

---

**Denis:** Hi everyone, kicking off planning. From the last sprint we closed 18 of 22 story points — the two 1C integration tasks slipped. Today I want to cover three blocks: new customer onboarding, the background analytics rebuild, and queue tech debt.

**Anya:** On queues. I looked at the workers — we hit Redis Streams limits once parallel jobs go above a thousand. I propose we start migrating to RabbitMQ this sprint. Not the whole pipeline, just the bulk product import. That's 5 story points.

**Lyosha:** I'm in favor, but let's add memory-consumption metrics on Redis first. Without those we can't prove the migration is even necessary — the budget review already asked me about it.

**Denis:** Okay, one point for the metrics, and then bulk-import migration is the next step, not this sprint. This sprint: instrumentation only.

**Anya:** Agreed.

**Mark:** On onboarding. Sonya finished the new wizard mockups, we're ready to build. Five steps instead of the current three, but with a progress bar and a skip option. Estimate is 8 points.

**Sonya:** One clarification: the product-import step has two branches — CSV and warehouse-system integration. I only drew the CSV variant; integration is still in research mode.

**Denis:** Good. Then we take only the CSV branch this sprint; the integration variant goes in the sprint after the research lands.

**Lyosha:** I have a concern. Production DB is growing faster than we planned — 40 GB added this quarter. If we do nothing, we hit the instance limit in two months. We either archive old events or migrate to a bigger instance. Both take time.

**Denis:** That's critical. Let's take a 2-point research task into the sprint: figure out which option is cheaper and bring numbers to the next planning. Anya, can you help estimate the archive volume?

**Anya:** Yes, I'll have a sample by Wednesday.

**Mark:** Last frontend item — Safari export bug in reports, two weeks old. Not critical but customers complain. I'll take 1 point.

**Denis:** Sprint totals: Redis metrics (1), CSV onboarding wizard (8), DB-storage research (2), Safari fix (1), plus 4-point buffer for bug fixes. 16 total. Matches our average velocity.

**Sonya:** In parallel I'll start the integration-branch wizard so we have mockups ready for the next sprint.

**Denis:** Great. Closing. Daily at the usual time.

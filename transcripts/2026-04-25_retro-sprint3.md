# Sprint Retrospective — Q2 Sprint 3

**Date:** 2026-04-25
**Attendees:** Denis, Anya, Mark, Sonya, Lyosha

---

**Denis:** We closed 14 of 16 points. Onboarding wizard is in prod, Redis metrics are flowing, archival research is almost done. What went well, what went badly, what we change.

**What went well**

**Mark:** The wizard shipped ahead of schedule, we got an extra QA pass. Sonya was always available, no waiting three days for mockups.

**Sonya:** Agree, review pace was great. I was able to answer same-day.

**Anya:** The read-replica for research — turned out useful beyond archival, I also ran EXPLAINs there and found two unoptimized queries. One of them is the top-1 slowest in our APM. Credit to Lyosha for setting up access quickly.

**What went badly**

**Lyosha:** The Safari fix stretched from one point to three. Mark, no offense.

**Mark:** None taken. I underestimated — turned out to be three different bugs, not one, and I had to redo the progress-bar render. Lesson learned: for "easy" Safari bugs I budget 3x on the estimate.

**Denis:** Logged as a team learning.

**Anya:** It worries me that we didn't finish archival. We estimated the research at 2 points, it took 5. I underestimated how messy the old migrations are — I had to figure out what each table actually holds before I could plan archival.

**Denis:** Not "badly" — "harder than it looked". Next sprint we continue and bring a concrete plan with numbers.

**Sonya:** My bad — I never started the integration-branch wizard because all my time went into reviewing the CSV branch. Which means next sprint we'll be waiting on mockups.

**Denis:** Got it. Next sprint, Sonya gets a dedicated design block, protected from review requests.

**What we change**

1. All estimates for Safari / mobile-browser frontend bugs — 3x the initial estimate, as buffer.
2. Design gets protected design time (min 2 days per week); reviews are batched.
3. Before any work on historical data — an exploratory session, not counted as an implementation point.

**Denis:** Recorded. Thanks all.

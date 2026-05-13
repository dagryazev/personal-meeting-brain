# Product Strategy — Q3 2026

**Date:** 2026-05-06
**Attendees:** Denis (PM), Masha (CEO), Anya (Backend lead), Sonya (Design lead)

---

**Masha:** Q2 we grew revenue 28%, added 14 new customers, retention is 94%. That's good. I want Q3 themed around "verticalization" — pick 1-2 industries and go deep.

**Denis:** From NPS and customer interviews we have two dominant user groups: e-commerce fulfillment (Acme and similar) and manufacturing warehouses (Tornado, Steelco, Vipra). Very different requirements. E-com wants fast pick-and-pack and marketplace integrations. Manufacturing wants serial-number tracking, batches, expiration dates.

**Masha:** Which group closes faster?

**Denis:** E-com. We already have most of what they need, except proper Ozon and Wildberries integrations. Manufacturing is at least a six-month roadmap.

**Anya:** Technically each marketplace integration is two weeks, given a stable API. Ozon is stable, Wildberries is not. WB needs retry logic and buffering.

**Masha:** E-com it is. Denis, draft a quarterly roadmap — three big features plus minor ones.

**Denis:** Proposal:
1. Ozon integration (full, with automatic label dispatch).
2. Wildberries integration (basic, no automated returns).
3. Excel export with formula templates — all three e-com customers asked for it, not just Acme.

Plus minor items: rename long field labels, optimize the mobile warehouse view.

**Sonya:** The mobile view isn't "minor". Acme and two others asked for a dedicated tablet interface. It needs research and design, not quick polish.

**Denis:** Agreed, promoting it to a major. Then: Ozon, WB, Excel export, mobile warehouse view. Four bigs.

**Anya:** Four is a lot. Realistically we close 2-3 in a quarter.

**Masha:** What are you willing to drop?

**Denis:** Wildberries. They're unstable and only two customers really need it. Push to Q4.

**Masha:** Agreed.

**Sonya:** In parallel I'll start the research on the manufacturing vertical — five interviews so we have signal on what they need by Q4.

**Masha:** Yes. And a separate ask of Denis: I want weekly retention and ARPU reports. Right now they're monthly and I catch shifts with a lag.

**Denis:** I'll build a Metabase dashboard and ping you with a summary every Monday.

**Masha:** Perfect.

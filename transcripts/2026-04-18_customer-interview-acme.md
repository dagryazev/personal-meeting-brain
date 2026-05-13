# Customer Interview — Acme Logistics

**Date:** 2026-04-18
**Attendees:** Denis, Sonya, Viktor Orlov (Head of Ops, Acme Logistics)

---

**Denis:** Viktor, thanks for taking the time. We want to understand how your team is working with our system after the first month — what hurts, what works.

**Viktor:** Sure. Short version — we're happy, but there are three big pains.

**Denis:** Listening.

**Viktor:** First — reports. We need Excel, not PDF, with editable formulas. CSV export exists today, but our customers — our customers — send those CSVs back with edits, and we merge by hand. If we could download xlsx with formulas already wired up, that would save an operator a full day a week.

**Sonya:** Noted. Excel export with formula templates.

**Viktor:** Second — mobile UI for warehouse staff. They're on tablets in the warehouse, and the web UI is slow on them. Especially barcode product lookup — the screen takes five seconds to refresh after a scan.

**Denis:** That's a known problem, we're profiling the frontend right now. Our measurements say the bottleneck isn't the network, it's rendering a large table. If we ship a dedicated mobile view, it'll fly.

**Viktor:** If you ship that this quarter, we're willing to pay extra to prioritize.

**Denis:** Let's talk separately. Third pain?

**Viktor:** Serial number tracking. Part of our inventory is electronics, each unit has a serial. Today we put them in a free-text field and can't search the history of a specific unit afterwards. We'd want first-class serial-number support.

**Sonya:** That's a structural data-model change, right?

**Denis:** Yes. That's a half-year project, but I've kept it in the backlog since last autumn. After your ask, it's probably tipping the scale.

**Viktor:** And a small one — the field label "Counterparty legal entity" is too long, it truncates in the table.

**Sonya:** That we'll fix in a day.

**Denis:** Viktor, what's working well for you?

**Viktor:** The 1C integration via the connector. Rock solid, unlike what we had before. And support is responsive — Anya helped us with import setup, sorted it in half an hour in chat.

**Denis:** Thanks, I'll pass it along. Recap of your priorities: Excel export, mobile warehouse view, serial-number tracking.

**Viktor:** In that order.

**Denis:** Talk next week.

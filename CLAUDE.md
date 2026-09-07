# Context for Claude Code

Read `docs/PROJECT_GOALS.md`, `docs/ARCHITECTURE.md`, and `docs/STATE.md`
before making non-trivial changes — they explain *why* the code is
structured the way it is, not just what it does.

## Rules that must not be broken

1. **Never let `app/payments/founder_donation.py` make a server-side
   Stripe API call or touch `STRIPE_PLATFORM_SECRET_KEY`.** It must stay a
   pure redirect to the founder's own payment link. This is a deliberate
   regulatory boundary, not an oversight — see `docs/ARCHITECTURE.md`,
   "Two separate Stripe flows."
2. **Never render `FounderProfile.external_url` in an iframe.** Always a
   plain external link (`target="_blank"`). See `docs/ARCHITECTURE.md`,
   "Discovery layer, not a host."
3. **Never present a compliance badge as a security guarantee.** Wording
   must stay "met criteria X as of date Y" — see the disclaimer already in
   `templates/marketplace/project.html`.
4. Any change to `app/compliance/service.py::run_basic_scan` should be
   about wiring in the real nis2.store/BSI A5 engine — it's currently a
   documented stub, not a bug.

## Current priority (per docs/ROADMAP.md, Phase 1)

Get this running locally with real data — Andrii's own ~15 portfolio
projects as the first listings — before adding new features. See
`docs/STATE.md` for exactly what's stubbed vs. real.

# Suggested Roadmap

Not a deadline-driven plan — priority is a complete, working, useful
product over speed (see `PROJECT_GOALS.md`). This is a suggested order
based on dependencies, not a schedule.

## Phase 1 — Make it real for yourself first

1. Set up `.env` with real values, run migrations, seed, log in as
   superadmin.
2. Add your own ~15 portfolio projects as the first listings (as
   superadmin, you can grant them an active subscription immediately
   instead of going through the paid flow).
3. Write real pitch-bot instructions for 2-3 of them and test the chatbot
   end-to-end with a real `ANTHROPIC_API_KEY`.
4. Fix anything that breaks under real content (long descriptions, missing
   fields, unusual URLs).

## Phase 2 — Wire in the compliance engine

5. Decide which integration approach fits your nis2.store/BSI A5 codebase
   best (see the three options documented in
   `app/compliance/service.py`) and implement it for real.
6. Decide whether scans run synchronously or need a background queue —
   likely needed once the real engine is doing actual work rather than
   the current instant stub.

## Phase 3 — Harden payments before real money moves

7. Create real Stripe Price objects — one per (tier x billing period), six
   total (`presentation`/`ai_pitch`/`payments` x monthly/annual) — in your
   own Stripe Dashboard, and test the platform subscription checkout
   end-to-end in test mode for each tier.
8. ~~Add proper webhook signature verification~~ — done
   (`stripe.Webhook.construct_event`, see `docs/STATE.md`). Still worth
   testing against a real webhook via `stripe listen --forward-to ...`
   before going live.
9. Write your platform Terms of Service and Datenschutz — required before
   you can plausibly ask anyone else to pay you a subscription or send
   visitors through donation links.

## Phase 4 — Open it up beyond yourself

10. Invite a small number of trusted outside founders to register and go
    through the real moderation flow — watch for friction points in the
    10-minute setup promise.
11. Add German `.po` translations once templates are wrapped in Babel's
    `_()` calls.
12. Add basic analytics (card views, external-link clicks, donation
    clicks) — useful both for you and as a value-add you can show
    founders.

## Later / only if the model proves out

13. ~~Revisit whether editing a published profile should always force
    re-review, or only for substantive changes~~ — done (2026-09-10):
    only substantive fields trigger re-review now, see `ARCHITECTURE.md`.
14. Search, pagination, image optimization — once catalog size actually
    needs them.
15. Email notifications for moderation decisions and subscription events.
16. Only with legal counsel: revisit equity crowdfunding or utility-token
    donations — both were explicitly deferred in `PROJECT_GOALS.md` for
    good reason, not as an oversight.

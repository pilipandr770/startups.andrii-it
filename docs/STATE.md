# Current State — what's real vs. stubbed

Written at handoff time so you know exactly what to trust and what to
build next. Nothing below is guesswork — it reflects what's actually in
the code right now.

## ✅ Fully working (real logic, not mocked)

- **Auth:** registration, login, logout, password hashing, role-based
  redirects (founder/admin/superadmin land on different pages).
- **Founder profile CRUD:** create/edit listing, file uploads (banner
  image, pitch deck PDF) saved to disk with unique filenames, slug
  generation with collision handling.
- **Moderation workflow:** draft → pending_review → published/rejected/
  suspended state machine, enforced in routes; editing a published profile
  correctly resets it to draft for re-review.
- **Marketplace catalog:** filtering by category and stage, public project
  page, correctly hides non-published profiles from the public (but lets
  the owner and staff preview them).
- **Two-Stripe-flow separation:** the architecture itself (see
  `ARCHITECTURE.md`) is implemented as written — `platform_subscription.py`
  and `founder_donation.py` are genuinely independent, and the donation
  route is a pure redirect with zero API calls.
- **Platform subscription (Stripe):** real Checkout Session creation and a
  webhook handler that updates `Subscription` status — signature-verified
  via `stripe.Webhook.construct_event` (see `payments/routes.py`; refuses
  to process anything if `STRIPE_PLATFORM_WEBHOOK_SECRET` isn't set, or if
  the signature doesn't check out). **Untested against a live Stripe
  account** — you'll need to create the actual Price objects in your
  Stripe Dashboard (one per tier x period — see below) and drop the IDs
  into `.env`, then test with Stripe's test mode and CLI
  (`stripe listen --forward-to ...`).
- **Three feature tiers** (`SubscriptionTier` in `app/models/subscription.py`,
  cumulative): `presentation` (listing only) -> `ai_pitch` (+ the AI pitch
  bot actually responds) -> `payments` (+ the donation button is shown and
  `/payments/donate/<slug>` works). Enforced both in templates (hide the
  UI) and routes (`chatbot/routes.py`, `payments/routes.py` — refuse the
  action server-side too, since a determined visitor could hit those
  routes directly). Superadmin's "Grant subscription" always grants the
  full `payments` tier (for Andrii's own projects). Dashboard shows a
  3-column tier comparison with Monthly/Annual subscribe links per tier.
- **Anti-scam guardrails on the donation flow:** `founder_stripe_payment_link`
  must resolve to a `stripe.com` hostname (checked by suffix, not
  substring — `app/founder/forms.py::stripe_hosted_link`) — we don't do our
  own KYC, we just require the link be provably Stripe's own, since Stripe
  verifies whoever owns it. `donation_terms` becomes required the moment a
  payment link is set. `legal_entity_name` (on `User`, editable from the
  profile form now, not just at registration) is also required before a
  payment link can be added. An admin approving a listing that has a
  payment link additionally flips `User.is_legal_entity_confirmed` — the
  human moderation step doubles as the legal-entity check. The moderation
  queue (`admin/queue.html`) now surfaces the owner's legal entity name and
  the full donation link/goal/terms so a moderator can actually judge them.
- **AI pitch bot:** real Anthropic API call with a guardrail system prompt
  that scopes the bot to the founder's own stated facts. Falls back to a
  clearly-labeled placeholder message if `ANTHROPIC_API_KEY` is missing —
  so the UI is testable without a key.
- **Superadmin panel:** view all users/profiles, unpublish anything,
  manually grant subscriptions (for Andrii's own projects), promote a
  founder to admin.
- **i18n plumbing:** Flask-Babel is wired up, language switcher works,
  `Category` model stores bilingual names — but **no `.po` translation
  files have been written yet** (see below).
- **Tests:** a small smoke-test suite (`tests/test_basic.py`) covering app
  boot, registration, profile defaults, and category bilingual lookup, plus
  `tests/test_compliance_scan.py` for the scanner (22 tests: SSRF guards,
  header/content checks, mocked end-to-end scans).
- **Basic compliance scan** (`app/compliance/scanner.py` +
  `service.py::run_basic_scan`): real, not a stub — an automated HTTP-based
  hygiene check of the founder's own `external_url` (HTTPS enforcement, TLS
  cert validity, security headers, mixed content, cookie flags), scored and
  stored per-check as `ComplianceScan.findings_json`. Only ever awards
  `BadgeLevel.BASIC_VERIFIED` or leaves it at `NONE` — see below for the
  deeper tiers. Hardened against SSRF (resolves + validates the target IP
  before every connection and redirect hop, blocks private/loopback/
  link-local/reserved addresses, only http/https, strict timeouts, response
  size cap) since it fetches a founder-supplied URL server-side; see the
  module docstring for the documented residual limitation (DNS-rebinding
  TOCTOU gap, accepted for this threat model). A 5-minute cooldown per
  profile guards against abuse via the scan button.
  **All plain (non-WTForms) POST forms across the app were also missing
  CSRF tokens** (moderation approve/reject, superadmin unpublish/grant/
  promote, founder submit-for-review, and this scan button) — found while
  wiring up the scan button, since CSRFProtect is applied app-wide. Fixed
  by adding a hidden `csrf_token` input to each; worth double-checking any
  *new* plain-HTML form for the same omission going forward.

- **Deep scan / "known vulnerabilities" report** (2026-09-10, same
  `scanner.py`, `scan_url(..., deep=True)`): an opt-in, subscription-gated
  perk — explicitly framed as a best-effort report against public data, NOT
  a penetration test, and deliberately excludes any port scanning (the
  resolved IP is often shared hosting — scanning its ports would touch
  other tenants' infrastructure without their consent and risks getting
  this platform's own Hostinger VPS abuse-reported, per that host's AUP).
  Adds three passive checks on top of the basic scan, gated behind
  `FounderProfile.vuln_scan_consent_given_at` (explicit opt-in, separate
  consent from the free basic scan) plus `subscription.is_active` (any
  status — trial counts):
    - software/version fingerprints already visible in the response
      (Server/X-Powered-By headers, `<meta name="generator">`, common JS
      filenames like `jquery-3.4.1.min.js`) looked up against the public
      NVD CVE database (`services.nvd.nist.gov`, no API key — fine at this
      volume, keyword search so results can be noisy, disclosed as such)
    - SPF/DMARC DNS TXT records (email spoofing protection)
    - a short fixed list of sensitive paths (`.env`, `.git/config`, etc.)
      fetched on the same already-SSRF-validated host
  Deep findings carry `category="deep"` and never affect score/badge_level
  — they're shown to the founder only (dashboard), never on the public
  project page (STATE.md keeps calling this out: never let a compliance
  signal overclaim — a *lack* of found CVEs must not read as "verified
  secure", so the report stays private and explicitly best-effort).

- **Docker deployment validated end-to-end** (2026-09-07): built the image
  and ran the full `docker-compose.yml` stack locally (web + Postgres) —
  found and fixed two real bugs in the process that only show up outside
  the test config (`TestingConfig` disables CSRF, which was masking both):
  1. **Both `/payments/webhook/stripe-platform` and `/chatbot/<slug>/message`
     were unreachable** — global `CSRFProtect` was rejecting every request
     to them with "400 CSRF token missing", since neither a Stripe webhook
     nor an anonymous visitor's `fetch()` call can carry a CSRF token. Now
     `@csrf.exempt` on both (see the docstring/comment at each route for
     why that's the correct fix, not a weakening — Stripe's own signature
     check and the chatbot's public/unauthenticated nature are the actual
     controls). Regression-guarded in `tests/test_payments.py` via a
     dedicated fixture that actually enables CSRF (`TestingConfig` doesn't,
     so a normal test wouldn't have caught this).
  2. **`web` could start and run migrations before Postgres was ready to
     accept connections** — `depends_on: [db]` only waits for the container
     to start, not for Postgres itself. Added a `pg_isready` healthcheck to
     `db` and changed `web`'s `depends_on` to `condition: service_healthy`.
  Also added `docker-entrypoint.sh` (runs `flask db upgrade` — idempotent —
  before `exec`'ing gunicorn, so a redeploy can't forget to migrate), and
  dropped the obsolete `version:` key from `docker-compose.yml`.

## 🟡 Stubbed / placeholder — needs real work

- **Deeper compliance tiers** (`nis2_ready` / `full_audit` in
  `BadgeLevel`): still require your actual nis2.store/BSI A5 tooling —
  the automated scan above only ever earns `basic_verified`. The doc
  comment in `app/compliance/service.py` lists three concrete integration
  approaches to choose between (import as a module, internal HTTP call, or
  background job queue) for wiring in the real engine and granting these
  tiers.
- **German translations:** the `.po`/`.mo` files under
  `app/translations/de/LC_MESSAGES/` are empty placeholders. All UI text
  is currently hardcoded in English in the templates rather than wrapped
  in Babel's `{{ _('...') }}` — templates need that pass before real
  translation can happen.
- **Email notifications:** there's no email sending yet (e.g. "your
  listing was approved/rejected", "your subscription payment failed").
  `app/templates/emails/` exists as an empty folder for this.
- **Legal document pages:** the platform's own Terms of Service, Privacy
  Policy (Datenschutz), and Impressum are referenced in templates
  (`register.html` has a placeholder `<a href="#">terms</a>`) but don't
  exist as real pages yet.

## ❌ Not started

- Rate limiting / abuse protection on the public chatbot endpoint
  (currently anyone can POST to `/chatbot/<slug>/message` — fine for an
  MVP with a small catalog, but will need throttling before wider launch).
- Image resizing/optimization for uploaded banners (currently stored as-is).
- Search (only category/stage filtering exists — no free-text search).
- Analytics (card views, click-through to external site, donation clicks).
- Background job queue (Celery/RQ) — not needed yet since nothing here is
  slow, but will likely be needed once the real compliance scan engine
  (which may take real time) is wired in.
- Automated database migrations beyond the initial `flask db migrate` —
  `migrations/` is an empty folder ready for `flask db init`.

## Known rough edges worth knowing about

- ~~`edit_profile` resets a published profile to `draft` on ANY edit~~ —
  fixed 2026-09-10: only resets on substantive field changes now (see
  `ARCHITECTURE.md`, "Roles and moderation"). Found via real use — a
  founder uploading a new pitch deck PDF unpublished their whole listing,
  which read as a bug even though it was the documented original behavior.
- The chatbot widget's conversation history is kept client-side only (in a
  JS variable) — refreshing the page loses it. Fine for an MVP.
- No pagination on the marketplace grid or moderation queue — fine at
  current scale (a handful to a few dozen projects), will need it before
  it grows much further.

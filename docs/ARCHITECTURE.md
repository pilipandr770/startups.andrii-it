# Architecture

## Stack

- **Backend:** Flask (app-factory pattern), SQLAlchemy ORM, Flask-Migrate
- **Auth:** Flask-Login, three roles: `founder`, `admin`, `superadmin`
- **Forms:** Flask-WTF (CSRF protection built in)
- **i18n:** Flask-Babel, `en`/`de`
- **AI:** Anthropic API (`anthropic` package) — pitch bot only, for now
- **Payments:** `stripe` package — see "Two separate Stripe flows" below
- **DB:** SQLite for local dev (zero setup), PostgreSQL in production
- **Deployment:** Docker Compose + Nginx reverse proxy + Let's Encrypt,
  matching the pattern already used across Andrii's other projects (one
  VPS, one container per app, subdomain routing)

## Discovery layer, not a host

The platform never hosts a founder's actual product, Impressum, or
Datenschutz. `FounderProfile.external_url` is the founder's own,
independent website — we only link to it (`target="_blank"`, plain
`<a href>`), never iframe it. This was a deliberate choice over embedding:

- Many sites block iframing via `X-Frame-Options` / CSP — plain links
  always work.
- It keeps the legal boundary unambiguous: the founder's Impressum belongs
  to the founder's own site, never to something that looks like part of
  ours.

Practical effect: `FounderProfile` only stores marketing/discovery
metadata (name, tagline, description, banner, video, category, stage,
funding goal text) — never a mirror of the founder's actual legal pages.

## Two separate Stripe flows — do not merge these

This is the single most important architectural rule in the codebase.
There are two entirely independent payment relationships, each using a
different Stripe account, and the code is deliberately split into two
modules to keep them from ever touching:

| | `app/payments/platform_subscription.py` | `app/payments/founder_donation.py` |
|---|---|---|
| Who pays whom | Founder → Andrii | Visitor → Founder |
| Whose Stripe account | Andrii's (`STRIPE_PLATFORM_SECRET_KEY`) | Founder's own (their `founder_stripe_payment_link`) |
| What the code does | Creates a real Stripe Checkout Session, listens for webhooks, updates `Subscription` | Pure redirect — no API calls, no funds ever touch our server |
| Regulatory shape | Ordinary B2B SaaS subscription | We are not a party to this transaction at all |

**Do not add Stripe Connect, split payments, or any server-side charge
creation to the donation flow.** The moment the platform's Stripe account
touches a visitor's donation, the legal picture changes substantially
(payment-service-provider obligations, KYC/AML exposure, holding client
funds). Keeping it a pure redirect is what keeps this simple.

## Compliance badge — legal wording matters

The badge (`ComplianceScan.badge_level`) must always be presented as
"met criteria X as of date Y" — never as a general security guarantee.
This is enforced in two places already:

- `docs/PROJECT_GOALS.md` and the model docstring in
  `app/models/compliance_scan.py` state the rule.
- `templates/marketplace/project.html` renders an explicit disclaimer line
  under the badge.

When wiring in the real nis2.store/BSI A5 engine (see `STATE.md`), keep
this wording discipline — don't let "NIS2-Ready" read as "this project is
secure."

## Donation terms must be unambiguous per project

`FounderProfile.donation_terms` exists specifically so each founder states,
in their own words, what a supporter gets in return for a donation. The
form label enforces this at the point of entry (see
`app/founder/forms.py::ProfileForm.donation_terms`). This protects both the
founder and the platform from a donation being reinterpreted as an
unregistered securities offering — a pre-order/reward framing avoids that,
an unclear "invest in us" framing does not.

## Roles and moderation

- `founder` — can only manage their own single `FounderProfile` (1:1 with
  `User`, enforced via a unique FK).
- `admin` — can approve/reject/suspend any `FounderProfile` via the
  moderation queue (`/admin/queue`). Promoted manually by a superadmin.
- `superadmin` — everything an admin can do, plus direct access to every
  user and profile, manual subscription grants (used for Andrii's own ~15
  projects, which don't pay the platform subscription), and the ability to
  unpublish anything at any time.

Every new listing starts in `draft`, moves to `pending_review` when the
founder submits it, and only becomes publicly visible once an admin
approves it (`published`). Any edit to a published profile currently
resets it back to `draft` — see `app/founder/routes.py::edit_profile` —
so re-review happens on every content change. This is a deliberate
starting point for a manual-moderation-only MVP; revisit if it creates too
much re-review overhead as the catalog grows (see `ROADMAP.md`).

## Directory structure

```
app/
├── __init__.py          # App factory, blueprint registration
├── config.py            # Dev/Prod/Test config classes
├── extensions.py        # db, login_manager, migrate, babel, csrf
├── decorators.py         # @admin_required, @superadmin_required
├── seed.py               # `flask seed` — categories + bootstrap superadmin
│
├── models/                # One file per entity (see docs/STATE.md for schema)
├── auth/                  # register, login, logout
├── founder/               # dashboard, profile form, chatbot config form
├── marketplace/           # public catalog + project detail page
├── chatbot/               # AI pitch bot: service.py (Claude call) + routes.py (API)
├── compliance/            # scanner.py (real basic-hygiene checks) + service.py + route
│                          #   nis2_ready/full_audit tiers still STUB — see STATE.md
├── payments/              # the two separate Stripe flows (see above)
├── admin/                 # moderation queue
├── superadmin/            # full access panel
│
├── static/{css,js,uploads}/
└── templates/{auth,founder,marketplace,admin,superadmin,emails}/
```

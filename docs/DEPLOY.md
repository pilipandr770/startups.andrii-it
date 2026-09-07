# Deploying to the VPS

The shared VPS (Hostinger, `187.124.6.120`, `srv1425385.hstgr.cloud`) already
runs one Traefik instance (`/docker/traefik-8r2b`) that owns ports 80/443
for every app on the box, routing by Docker labels and terminating TLS via
Let's Encrypt through Cloudflare's DNS-01 challenge (`cfdns` resolver — see
`/docker/traefik-8r2b/docker-compose.yml`). **Use `docker-compose.traefik.yml`
for this app, not `docker-compose.yml`** (that one assumes a dedicated
Nginx+certbot setup this VPS doesn't use — kept for reference/other hosts).

This app's compose files were built and smoke-tested locally on
2026-09-07 (full stack: gunicorn + Postgres + migrations + seed, verified
over HTTP) — see `docs/STATE.md` for what that testing found and fixed
(two real CSRF-related bugs, a Postgres startup race).

## 1. DNS (done)

`startups.andrii-it.de` -> `187.124.6.120`, A record, DNS-only (grey
cloud) in Cloudflare — added 2026-09-07, matching the pattern already used
by `botteu.andrii-it.de` and `nis2.andrii-it.de` on the same VPS (Traefik
handles TLS directly via the DNS-01 challenge; the Cloudflare proxy layer
isn't needed on top of that for this app).

## 2. Get the code onto the VPS

```bash
git clone https://github.com/pilipandr770/startups.andrii-it.git startup-showcase
cd startup-showcase
```

## 3. Production `.env`

Copy `.env.example` to `.env` and fill in real values. Critical differences
from local dev:

- `FLASK_ENV=production` (turns off Flask's debug mode — leaving this as
  `development` would expose the interactive debugger to the internet)
- `SECRET_KEY` — `python3 -c "import secrets; print(secrets.token_hex(32))"`
- `POSTGRES_PASSWORD` — a real value (the compose file builds `DATABASE_URL`
  from this automatically, no need to also set `DATABASE_URL` by hand)
- `SUPERADMIN_EMAIL` / `SUPERADMIN_PASSWORD` — real login
- `BASE_URL=https://startups.andrii-it.de` (used to build Stripe Checkout
  success/cancel URLs)
- `TRAEFIK_DOMAIN=startups.andrii-it.de` and `TRAEFIK_CERTRESOLVER=cfdns`
  (add these two — they're not in `.env.example` since they're specific to
  this VPS's Traefik setup, referenced by `docker-compose.traefik.yml`)
- The six `STRIPE_PLATFORM_PRICE_ID_*` vars, `STRIPE_PLATFORM_SECRET_KEY`,
  `STRIPE_PLATFORM_PUBLISHABLE_KEY`, `STRIPE_PLATFORM_WEBHOOK_SECRET` — see
  step 5.
- `ANTHROPIC_API_KEY` — for the pitch bot to actually respond.

## 4. Bring the stack up

```bash
docker compose -f docker-compose.traefik.yml up -d --build
```

Migrations run automatically on container start (`docker-entrypoint.sh`).
First time only, seed categories + bootstrap the superadmin account:

```bash
docker compose -f docker-compose.traefik.yml exec web flask seed
```

Traefik picks the new container up automatically via its Docker label
provider — no Traefik restart or config edit needed. Check
`https://startups.andrii-it.de` within a minute or two; the ACME
certificate is issued on first request to that router.

## 5. Stripe: connect the real webhook

Once `https://startups.andrii-it.de` is live:

1. Stripe Dashboard -> Developers -> Webhooks -> Add endpoint.
2. Endpoint URL: `https://startups.andrii-it.de/payments/webhook/stripe-platform`
3. Events to send: at minimum `checkout.session.completed`,
   `customer.subscription.updated`, `customer.subscription.deleted` (see
   `app/payments/platform_subscription.py::handle_webhook_event`).
4. Copy the endpoint's **Signing secret** into `STRIPE_PLATFORM_WEBHOOK_SECRET`
   in `.env`, then `docker compose -f docker-compose.traefik.yml up -d` to
   pick it up (the route refuses to process anything if this is unset).
5. Create the six recurring Prices (`presentation`/`ai_pitch`/`payments` x
   monthly/annual) in Stripe Dashboard -> Product catalog, and drop their
   IDs into the matching `STRIPE_PLATFORM_PRICE_ID_*` vars.
6. Test with Stripe CLI or a real test-mode checkout before trusting it
   with real money.

## Redeploying after a code change

```bash
git pull
docker compose -f docker-compose.traefik.yml up -d --build
```

Migrations re-run automatically and are a no-op if nothing changed.

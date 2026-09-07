# Deploying to the VPS

Matches the pattern already used for Andrii's other projects: one shared
VPS, one Docker Compose stack per app, a shared Nginx reverse proxy routing
by subdomain, Let's Encrypt via certbot. See `docs/ARCHITECTURE.md`.

This app's `docker-compose.yml` and `Dockerfile` were built and smoke-tested
locally on 2026-09-07 (full stack: gunicorn + Postgres + migrations +
seed, verified over HTTP) — see `docs/STATE.md` for what that testing
found and fixed. What's below has NOT yet been run against the real VPS.

## 1. Get the code onto the VPS

```bash
# On the VPS, in whatever directory holds your other projects' repos:
git clone <this-repo-url> startup-showcase
cd startup-showcase
```

(If this project isn't pushed to a git remote yet, that's step zero —
ask before doing this if you want it kept private initially.)

## 2. Production `.env`

Copy `.env.example` to `.env` on the VPS and fill in real values. Critical
differences from local dev:

- `FLASK_ENV=production` (NOT `development` — this is what turns off Flask's
  debug mode; leaving it as `development` would expose the interactive
  debugger and stack traces to the public internet)
- `SECRET_KEY` — a real random value (`python -c "import secrets; print(secrets.token_hex(32))"`)
- `DATABASE_URL=postgresql://startupshowcase:<POSTGRES_PASSWORD>@db:5432/startupshowcase`
  (matching whatever you set `POSTGRES_PASSWORD` to — `docker-compose.yml`
  reads that from the environment, so either export it or add it to `.env`
  and reference it: `POSTGRES_PASSWORD=...` alongside `DATABASE_URL`)
- `SUPERADMIN_EMAIL` / `SUPERADMIN_PASSWORD` — your real login, real password
- `BASE_URL=https://<your-subdomain>` (used to build Stripe Checkout
  success/cancel URLs — must be the real public HTTPS URL)
- The six `STRIPE_PLATFORM_PRICE_ID_*` vars, `STRIPE_PLATFORM_SECRET_KEY`,
  `STRIPE_PLATFORM_PUBLISHABLE_KEY`, `STRIPE_PLATFORM_WEBHOOK_SECRET` — see
  step 5.
- `ANTHROPIC_API_KEY` — for the pitch bot to actually respond instead of
  showing the placeholder message.

## 3. Bring the stack up

```bash
docker compose up -d --build
```

Migrations run automatically on container start (`docker-entrypoint.sh`).
First time only, seed categories + bootstrap the superadmin account:

```bash
docker compose exec web flask seed
```

## 4. Nginx + subdomain + HTTPS

`nginx.conf` in the repo root is a template server block — adapt it into
your existing shared Nginx config the way your other subdomains are set
up, pointing `proxy_pass` at the `web` service. Then:

```bash
certbot --nginx -d <your-subdomain>
```

**DNS**: add an A record (or AAAA/CNAME, matching how your other subdomains
are set up) for `<your-subdomain>` -> the VPS's IP, in whichever DNS
provider hosts the parent domain. If that's Cloudflare and the record is
proxied (orange cloud), set Cloudflare's SSL/TLS mode to **Full (strict)**
once certbot has issued a real certificate on the origin — "Flexible" mode
would have Cloudflare talk to the VPS over plain HTTP, which is not what
you want for a login/payment flow. DNS-only (grey cloud) also works and is
simpler if you don't need Cloudflare's proxy features for this subdomain.

## 5. Stripe: connect the real webhook

Once `https://<your-subdomain>` is live:

1. Stripe Dashboard -> Developers -> Webhooks -> Add endpoint.
2. Endpoint URL: `https://<your-subdomain>/payments/webhook/stripe-platform`
3. Events to send: at minimum `checkout.session.completed`,
   `customer.subscription.updated`, `customer.subscription.deleted` (see
   `app/payments/platform_subscription.py::handle_webhook_event` for
   exactly what's handled).
4. Copy the endpoint's **Signing secret** into `STRIPE_PLATFORM_WEBHOOK_SECRET`
   in `.env` on the VPS, then `docker compose up -d` to pick it up (the
   route refuses to process anything if this is unset — see
   `docs/STATE.md`).
5. Create the six recurring Prices (`presentation`/`ai_pitch`/`payments` x
   monthly/annual) in Stripe Dashboard -> Product catalog, and drop their
   IDs into the matching `STRIPE_PLATFORM_PRICE_ID_*` vars.
6. Test with Stripe CLI against the live endpoint, or trigger a real test-mode
   checkout, before trusting it with real money.

## Redeploying after a code change

```bash
git pull
docker compose up -d --build
```

Migrations re-run automatically and are a no-op if nothing changed.

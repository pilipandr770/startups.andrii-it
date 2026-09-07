# Startup Showcase

A discovery marketplace where startup founders self-publish a listing card
that links out to their own, already-live project website — with an
AI pitch assistant, an optional compliance badge, and a direct donation
link to the founder's own Stripe account.

**This is a working code skeleton, not a finished product.** It implements
the full architecture agreed on so far, with real (not mocked) auth,
database models, forms, and routing. A few integration points are
intentionally left as stubs — see `docs/STATE.md` for exactly what's real
vs. placeholder.

## Quick start (local dev)

```bash
cd startup-showcase
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# edit .env: at minimum set SECRET_KEY, SUPERADMIN_EMAIL, SUPERADMIN_PASSWORD
# ANTHROPIC_API_KEY is needed for the pitch bot to give real answers —
# without it, it returns a clearly-labeled placeholder response.

flask db init
flask db migrate -m "initial schema"
flask db upgrade

flask seed        # creates categories + your superadmin account

flask run
```

Visit `http://localhost:5000`. Log in as your superadmin
(`SUPERADMIN_EMAIL` / `SUPERADMIN_PASSWORD` from `.env`) to reach
`/superadmin`. Register a normal account to try the founder flow.

## Where to read next

- **`docs/PROJECT_GOALS.md`** — what this platform is, who it's for, and the
  business/legal decisions already made (read this first).
- **`docs/ARCHITECTURE.md`** — how the pieces fit together and *why*,
  especially the two separate Stripe flows and the "discovery layer, not a
  host" legal positioning.
- **`docs/STATE.md`** — an honest list of what's fully working vs. stubbed,
  so you know exactly what to build next.
- **`docs/ROADMAP.md`** — suggested next steps, in order.

## Deployment

`Dockerfile` + `docker-compose.yml` + `nginx.conf` are set up to match your
existing VPS pattern (Nginx reverse proxy, one container per app, Let's
Encrypt via certbot) — see comments in `nginx.conf` for the exact steps.

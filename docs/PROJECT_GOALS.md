# Project Goals

## What this is

A discovery marketplace for startup founders — a place to get a public
listing, an AI assistant that pitches your project 24/7 in any language,
an optional security/compliance badge, and a simple way for visitors to
support you financially — without giving up control of your own project
or its legal footprint.

Priority is stated explicitly (not speed): build a complete, genuinely
useful, working project with real monetization potential. Deadlines are
secondary to getting the model right.

## Who it's for

- **Founders (supply side):** Andrii's own ~15 portfolio projects (added
  continuously) plus outside founders — especially people building with
  AI-assisted ("vibe coding") tools, who often have a working product but
  little time for marketing, English-language pitching, or being online
  around the clock.
- **Visitors (demand side):** potential investors, early customers, and
  people who just want to support an interesting project — filtering by
  category/stage, getting a fast visual read on a project, and being able
  to ask questions without a language or timezone barrier.

## Core value loop

1. A founder with an already-live project and a registered legal entity
   registers, fills in their dashboard (link, banner, video, description,
   funding goal, donation terms, Stripe payment link) in about ten minutes.
2. They write a short brief for their AI pitch assistant — this is the key
   unlock: it removes the language barrier and the "founder isn't online"
   problem entirely.
3. Andrii manually reviews and approves the listing (moderation queue).
4. The published card appears in the public catalog with filters.
5. Visitors browse, click through to the founder's own live site to verify
   the project is real, chat with the AI assistant, and optionally donate
   or contact the founder directly.
6. Andrii earns a monthly/annual **platform subscription** from the founder
   for the listing — not a commission on funds raised.

## Key business decisions already made

- **Monetization:** flat subscription fee paid by the founder for the
  listing. No percentage commission on donations or investment at this
  stage — deliberately, to avoid becoming a financial intermediary (see
  `ARCHITECTURE.md`).
- **Payments:** Stripe only for now. Utility tokens were considered and
  explicitly deferred — under MiCA, utility tokens are regulated
  crypto-assets requiring a compliant whitepaper and possibly an issuer
  license. This is directly in Andrii's area of regulatory expertise
  (AI Act / NIS2 / MiCA), so it may become a deliberate Phase 2
  differentiator rather than an afterthought — but it is out of scope for
  this MVP.
- **Deal negotiation:** handled entirely by each founder, not the
  platform. The platform is a discovery layer, not a broker.
- **Content hosting:** founders must already have a live project website
  with their own Impressum/Datenschutz/contact form. The platform links
  out to it — it does not host, mirror, or iframe it.
- **Compliance badge:** built in as a marketplace feature (not sold as a
  separate product), leveraging Andrii's existing nis2.store / BSI A5
  tooling as the underlying scan engine (not yet wired into this
  skeleton — see `STATE.md`).
- **Moderation:** every listing is manually reviewed by Andrii via a
  superadmin panel before it goes live. No auto-publish at this stage.
- **Languages:** English and German.
- **Domain:** to be hosted as a subdomain of andrii-it.de.

## Explicitly out of scope for now

- Equity crowdfunding / selling ownership stakes (regulatory complexity is
  high; revisit only with legal counsel).
- Platform-side payment processing or fund custody of any kind.
- Utility token sales.
- Automated/AI-assisted moderation (manual only, for now).

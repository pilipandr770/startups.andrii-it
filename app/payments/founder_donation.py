"""
FLOW 2 of 2 — FOUNDER DONATIONS.

CRITICAL: the platform NEVER touches, holds, or processes these funds.
A visitor supporting a project is redirected to the FOUNDER's own Stripe
Payment Link (FounderProfile.founder_stripe_payment_link), which the founder
set up themselves in their own Stripe account.

Do NOT add Stripe Connect, split payments, or any server-side charge
creation here. Keeping this a pure redirect is what keeps the platform out
of payment-service-provider territory — see docs/ARCHITECTURE.md,
"Two separate Stripe flows" and "Regulatory positioning".
"""


def get_donation_redirect_url(founder_profile):
    """Returns the founder's own Stripe Payment Link, or None if not set."""
    return founder_profile.founder_stripe_payment_link or None

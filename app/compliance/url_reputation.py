"""
Checks a founder's public project link (FounderProfile.external_url)
against third-party URL/domain reputation databases before a human
moderator reviews the listing — an extra signal shown to the moderator,
never an automated gate. Per docs/PROJECT_GOALS.md, moderation stays
manual-only: a flagged result is surfaced prominently, but the moderator
still decides (false positives happen, especially for brand-new domains).

This is about protecting MARKETPLACE VISITORS, not the founder's own
site — see docs/ARCHITECTURE.md, "Two separate Stripe flows" and the
donation-link anti-scam checks for the same underlying goal: never let
this platform become a distribution vector for phishing or malware.

None of these checks connect to the founder's site at all — they only ask
third-party reputation databases about the domain, so there's no SSRF
surface here (unlike app/compliance/scanner.py, which does fetch the site).

Keyless, always on:
  - URLhaus (abuse.ch) — free public malware-URL/host database, no API key

Optional, only run if the corresponding env var is set (skipped with an
"unknown / not configured" finding otherwise — same graceful-degradation
pattern as ANTHROPIC_API_KEY elsewhere in this app):
  - Google Safe Browsing v4 — GOOGLE_SAFE_BROWSING_API_KEY
    (free tier: https://developers.google.com/safe-browsing, ~10k req/day)
  - VirusTotal v3 — VIRUSTOTAL_API_KEY
    (free public API key, low rate limit — fine for our volume)
"""

import base64
from dataclasses import dataclass
from urllib.parse import urlparse

import requests
from flask import current_app

USER_AGENT = "StartupShowcaseURLReputationCheck/1.0 (+https://andrii-it.de)"
TIMEOUT = (5, 8)

URLHAUS_HOST_API = "https://urlhaus-api.abuse.ch/v1/host/"
GSB_API = "https://safebrowsing.googleapis.com/v4/threatMatches:find"
VT_URL_API = "https://www.virustotal.com/api/v3/urls"


@dataclass
class ReputationFinding:
    source: str
    status: str  # "clean" | "flagged" | "unknown"
    detail: str


def _check_urlhaus(hostname):
    try:
        resp = requests.post(
            URLHAUS_HOST_API, data={"host": hostname},
            headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT,
        )
        data = resp.json()
    except Exception as exc:
        return ReputationFinding("URLhaus", "unknown", f"Lookup failed: {exc}")

    if data.get("query_status") != "ok":
        return ReputationFinding("URLhaus", "clean", "No known malware association.")

    urls = data.get("urls") or []
    active = [u for u in urls if u.get("url_status") == "online"]
    if not urls:
        return ReputationFinding("URLhaus", "clean", "No known malware association.")
    threat_types = {u.get("threat") for u in urls if u.get("threat")}
    status = "flagged" if active else "unknown"
    detail = (
        f"{'Currently' if active else 'Previously'} listed in URLhaus "
        f"({len(urls)} entr{'y' if len(urls) == 1 else 'ies'}, threat: {', '.join(threat_types) or 'unspecified'})."
    )
    return ReputationFinding("URLhaus", status, detail)


def _check_google_safe_browsing(url):
    api_key = current_app.config.get("GOOGLE_SAFE_BROWSING_API_KEY")
    if not api_key:
        return ReputationFinding("Google Safe Browsing", "unknown", "Not configured (no API key set).")

    payload = {
        "client": {"clientId": "startup-showcase", "clientVersion": "1.0"},
        "threatInfo": {
            "threatTypes": ["MALWARE", "SOCIAL_ENGINEERING", "UNWANTED_SOFTWARE", "POTENTIALLY_HARMFUL_APPLICATION"],
            "platformTypes": ["ANY_PLATFORM"],
            "threatEntryTypes": ["URL"],
            "threatEntries": [{"url": url}],
        },
    }
    try:
        resp = requests.post(GSB_API, params={"key": api_key}, json=payload, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        return ReputationFinding("Google Safe Browsing", "unknown", f"Lookup failed: {exc}")

    matches = data.get("matches")
    if not matches:
        return ReputationFinding("Google Safe Browsing", "clean", "No threats found.")
    threat_types = {m.get("threatType") for m in matches}
    return ReputationFinding("Google Safe Browsing", "flagged", f"Flagged as: {', '.join(threat_types)}.")


def _check_virustotal(url):
    api_key = current_app.config.get("VIRUSTOTAL_API_KEY")
    if not api_key:
        return ReputationFinding("VirusTotal", "unknown", "Not configured (no API key set).")

    url_id = base64.urlsafe_b64encode(url.encode()).decode().rstrip("=")
    try:
        resp = requests.get(
            f"{VT_URL_API}/{url_id}", headers={"x-apikey": api_key, "User-Agent": USER_AGENT}, timeout=TIMEOUT,
        )
        if resp.status_code == 404:
            return ReputationFinding("VirusTotal", "unknown", "Not yet analyzed by VirusTotal.")
        resp.raise_for_status()
        stats = resp.json()["data"]["attributes"]["last_analysis_stats"]
    except Exception as exc:
        return ReputationFinding("VirusTotal", "unknown", f"Lookup failed: {exc}")

    malicious = stats.get("malicious", 0)
    suspicious = stats.get("suspicious", 0)
    if malicious or suspicious:
        return ReputationFinding(
            "VirusTotal", "flagged",
            f"{malicious} engine(s) flagged malicious, {suspicious} suspicious (out of {sum(stats.values())}).",
        )
    return ReputationFinding("VirusTotal", "clean", f"0 engines flagged it (out of {sum(stats.values())}).")


def check_url_reputation(url):
    """Returns (overall_status, detail_text). overall_status is "flagged" if
    ANY source flags it, "clean" if at least one source came back clean and
    none flagged it, "unknown" if nothing could be checked (e.g. all
    optional sources unconfigured and URLhaus itself failed)."""
    hostname = urlparse(url).hostname or ""
    findings = [_check_urlhaus(hostname), _check_google_safe_browsing(url), _check_virustotal(url)]

    if any(f.status == "flagged" for f in findings):
        overall = "flagged"
    elif any(f.status == "clean" for f in findings):
        overall = "clean"
    else:
        overall = "unknown"

    detail = " | ".join(f"{f.source}: {f.detail}" for f in findings)
    return overall, detail

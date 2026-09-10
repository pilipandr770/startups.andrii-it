"""
Lightweight, self-contained "basic verified" security-hygiene scanner.

This checks a founder's PUBLIC external site (the one they already linked
in their listing and explicitly asked us to scan) for baseline web security
hygiene — the same class of checks tools like securityheaders.com or
Mozilla Observatory perform: HTTPS enforcement, TLS certificate validity,
security response headers, mixed content, cookie flags.

This is NOT the nis2.store / BSI A5 engine. That's a separate, deeper
integration reserved for the "nis2_ready" / "full_audit" tiers (see
docs/STATE.md and docs/ROADMAP.md, Phase 2) and is granted manually until
wired in. This module only ever produces BadgeLevel.BASIC_VERIFIED or
leaves the profile at BadgeLevel.NONE, with a findings report explaining
what to fix either way — useful feedback for the founder regardless of
whether the badge is earned.

SECURITY NOTE — this fetches a URL supplied by the founder (their own
external_url). Treat every URL as untrusted input:
  - resolve + validate the target IP before connecting, and again on every
    redirect hop, to block SSRF against private/loopback/link-local/reserved
    addresses (this also covers the cloud metadata IP 169.254.169.254, which
    falls under link-local)
  - only http/https schemes; redirects are followed manually (never rely on
    `requests`' auto-redirect, which would skip our validation)
  - strict connect/read timeouts and a response-size cap, so a slow or huge
    response can't be used to tie up a worker
  - a distinctive User-Agent so site owners can identify/allowlist this bot
Known residual limitation: IP validation happens right before each connect,
but the OS resolver is trusted at connect time too (classic TOCTOU / DNS
rebinding gap). Closing that fully would require pinning the validated IP
into the TLS/HTTP connection, which is real added complexity for a feature
whose threat model is "a founder scans their own asserted domain to earn a
badge, and a human still reviews the listing before it publishes." If this
scanner is ever repurposed to accept an arbitrary caller-supplied target
(not a founder's own registered external_url), revisit this.

DEEP SCAN ("known vulnerabilities report", scan_url(..., deep=True)) —
an opt-in, paid-tier-gated perk (see app/compliance/service.py and
app/compliance/routes.py for the consent + subscription gate). Explicitly
NOT a penetration test — no exploitation is attempted, ever. It adds three
kinds of passive, best-effort checks on top of the basic scan:
  - software/version fingerprints pulled from the SAME response already
    fetched (Server/X-Powered-By headers, <meta name="generator">, common
    JS library filenames) looked up against the public NVD CVE database
  - DNS security records (SPF/DMARC) via plain DNS TXT lookups — no
    connection to the target host at all
  - a short, fixed list of well-known sensitive paths (.env, .git/...)
    fetched on the SAME already-validated host, same SSRF guard as
    everything else here
Deliberately excludes any form of port scanning — the resolved IP is very
often shared hosting, and scanning ports on it would reach infrastructure
and tenants who never consented, and risks getting this platform's own VPS
abuse-reported. If deeper scanning (including port-level) is ever wanted,
it should be a separate, explicitly-scoped engine (see the real nis2.store
/ BSI A5 integration planned for the nis2_ready/full_audit badge tiers),
not bolted onto this one. Deep findings never affect score/badge_level —
they're reported to the founder only, not shown publicly (see
docs/STATE.md).
"""

import ipaddress
import re
import socket
import ssl
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

import dns.resolver
import requests

from app.models import BadgeLevel

USER_AGENT = "StartupShowcaseComplianceScanner/1.0 (+https://andrii-it.de)"
CONNECT_TIMEOUT = 5
READ_TIMEOUT = 8
MAX_BODY_BYTES = 2 * 1024 * 1024  # 2MB cap — plenty for a homepage's HTML
MAX_REDIRECTS = 5

# Points awarded per check when it passes. Informational/warn-only checks
# (version disclosure, cookie flags) don't affect the score.
POINTS = {
    "https": 25,
    "tls_cert": 15,
    "strict-transport-security": 15,
    "content-security-policy": 15,
    "x-content-type-options": 5,
    "referrer-policy": 5,
    "frame_protection": 10,
    "mixed_content": 10,
}
MAX_SCORE = sum(POINTS.values())
PASS_THRESHOLD = 70

SECURITY_HEADERS = [
    ("strict-transport-security", "HSTS (Strict-Transport-Security)"),
    ("content-security-policy", "Content-Security-Policy"),
    ("x-content-type-options", "X-Content-Type-Options"),
    ("referrer-policy", "Referrer-Policy"),
]

MIXED_CONTENT_RE = re.compile(rb'''(?:src|href)\s*=\s*["']http://[^"']+["']''', re.IGNORECASE)

# --- Deep scan constants -----------------------------------------------

NVD_API_URL = "https://services.nvd.nist.gov/rest/json/cves/2.0"
NVD_TIMEOUT = (5, 10)
MAX_CVES_PER_PRODUCT = 3

GENERATOR_META_RE = re.compile(
    rb'''<meta[^>]+name=["']generator["'][^>]+content=["']([^"']+)["']''', re.IGNORECASE
)
JQUERY_VERSION_RE = re.compile(rb'''jquery[.-]?(\d+\.\d+(?:\.\d+)?)(?:\.min)?\.js''', re.IGNORECASE)

# path -> a byte marker expected in a genuine hit, so a catch-all "200 for
# everything" site (common with SPA routing) doesn't produce false positives
SENSITIVE_PATHS = [
    ("/.env", b"="),
    ("/.git/HEAD", b"ref:"),
    ("/.git/config", b"[core]"),
    ("/wp-config.php.bak", None),
    ("/.DS_Store", None),
]


class ScanError(Exception):
    """Raised for anything that should stop the scan with a user-facing reason."""


@dataclass
class Finding:
    id: str
    label: str
    status: str  # "pass" | "fail" | "warn" | "info"
    detail: str
    category: str = "basic"  # "basic" (badge-affecting) | "deep" (report-only, see module docstring)


@dataclass
class ScanResult:
    badge_level: str
    score: int
    max_score: int
    findings: list = field(default_factory=list)

    @property
    def summary(self):
        passed = sum(1 for f in self.findings if f.status == "pass")
        return f"{passed}/{len(self.findings)} checks passed ({self.score}/{self.max_score} pts) as of {datetime.utcnow().strftime('%Y-%m-%d')}."

    def findings_as_dicts(self):
        return [asdict(f) for f in self.findings]


def _is_blocked_ip(ip_str):
    ip = ipaddress.ip_address(ip_str)
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def _resolve_and_validate(hostname):
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise ScanError(f"Could not resolve host '{hostname}': {exc}")

    ips = {info[4][0] for info in infos}
    if not ips:
        raise ScanError(f"No addresses resolved for host '{hostname}'.")

    for ip_str in ips:
        if _is_blocked_ip(ip_str):
            raise ScanError(
                f"Refusing to scan '{hostname}': resolves to a private/internal "
                f"address. Only public websites can be scanned."
            )
    return ips


def _validate_url(url):
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ScanError(f"Unsupported URL scheme '{parsed.scheme}'. Only http/https are allowed.")
    if not parsed.hostname:
        raise ScanError("URL has no hostname.")
    _resolve_and_validate(parsed.hostname)
    return parsed


def _safe_get(url):
    """Manual redirect loop: validate + resolve before EVERY hop, so a
    redirect can never smuggle the fetch to an internal address."""
    current_url = url

    for _ in range(MAX_REDIRECTS + 1):
        _validate_url(current_url)

        try:
            resp = requests.get(
                current_url,
                headers={"User-Agent": USER_AGENT},
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
                allow_redirects=False,
                stream=True,
            )
        except requests.exceptions.SSLError as exc:
            raise ScanError(f"TLS error connecting to '{current_url}': {exc}")
        except requests.exceptions.RequestException as exc:
            raise ScanError(f"Could not connect to '{current_url}': {exc}")

        if resp.status_code in (301, 302, 303, 307, 308):
            location = resp.headers.get("Location")
            resp.close()
            if not location:
                raise ScanError(f"Redirect from '{current_url}' had no Location header.")
            current_url = urljoin(current_url, location)
            continue

        body = b""
        for chunk in resp.iter_content(chunk_size=8192):
            body += chunk
            if len(body) >= MAX_BODY_BYTES:
                break
        return resp, body, current_url

    raise ScanError(f"Too many redirects (> {MAX_REDIRECTS}) starting from '{url}'.")


def _check_https(original_url, final_url):
    if urlparse(final_url).scheme == "https":
        if urlparse(original_url).scheme == "http":
            return Finding("https", "HTTPS enforced", "pass",
                            f"http:// redirects to https:// (ended at {final_url}).")
        return Finding("https", "HTTPS enforced", "pass", f"Served over HTTPS ({final_url}).")
    return Finding("https", "HTTPS enforced", "fail",
                    "Site is served over plain HTTP with no redirect to HTTPS.")


def _check_tls_cert(final_url):
    parsed = urlparse(final_url)
    if parsed.scheme != "https":
        return Finding("tls_cert", "Valid TLS certificate", "fail", "Site is not served over HTTPS.")

    hostname = parsed.hostname
    port = parsed.port or 443

    try:
        validated_ips = _resolve_and_validate(hostname)
        # Pin to a validated IP for this specific connection while keeping
        # correct SNI/hostname verification via server_hostname.
        target_ip = next(iter(validated_ips))
        ctx = ssl.create_default_context()
        with socket.create_connection((target_ip, port), timeout=CONNECT_TIMEOUT) as sock:
            with ctx.wrap_socket(sock, server_hostname=hostname) as ssock:
                cert = ssock.getpeercert()
    except ScanError:
        raise
    except Exception as exc:
        return Finding("tls_cert", "Valid TLS certificate", "fail", f"Could not verify certificate: {exc}")

    not_after_raw = cert.get("notAfter")
    if not not_after_raw:
        return Finding("tls_cert", "Valid TLS certificate", "warn", "Certificate presented but expiry could not be parsed.")

    not_after = datetime.strptime(not_after_raw, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
    days_left = (not_after - datetime.now(timezone.utc)).days
    if days_left < 0:
        return Finding("tls_cert", "Valid TLS certificate", "fail", f"Certificate expired {-days_left} day(s) ago.")
    if days_left < 14:
        return Finding("tls_cert", "Valid TLS certificate", "warn", f"Certificate expires soon ({days_left} days).")
    return Finding("tls_cert", "Valid TLS certificate", "pass",
                    f"Valid and hostname-matched, expires in {days_left} days.")


def _check_frame_protection(headers):
    csp = headers.get("content-security-policy", "")
    xfo = headers.get("x-frame-options", "")
    if "frame-ancestors" in csp.lower():
        return Finding("frame_protection", "Clickjacking protection", "pass", "frame-ancestors directive in CSP.")
    if xfo:
        return Finding("frame_protection", "Clickjacking protection", "pass", f"X-Frame-Options: {xfo}")
    return Finding("frame_protection", "Clickjacking protection", "warn",
                    "No X-Frame-Options or CSP frame-ancestors directive found.")


def _check_headers(headers):
    h = {k.lower(): v for k, v in headers.items()}
    findings = []
    for key, label in SECURITY_HEADERS:
        if key in h:
            findings.append(Finding(key, label, "pass", h[key][:200]))
        else:
            findings.append(Finding(key, label, "fail", "Header not present."))

    findings.append(_check_frame_protection(h))

    server = h.get("server")
    powered_by = h.get("x-powered-by")
    if server or powered_by:
        detail = ", ".join(filter(None, [server, powered_by]))
        findings.append(Finding("version_disclosure", "No version info leaked", "info",
                                 f"Server/X-Powered-By reveals: {detail}"))
    else:
        findings.append(Finding("version_disclosure", "No version info leaked", "pass",
                                 "No Server/X-Powered-By header disclosed."))
    return findings


def _check_mixed_content(final_url, body):
    if urlparse(final_url).scheme != "https":
        return Finding("mixed_content", "No mixed content", "info", "Skipped — page is not served over HTTPS.")
    matches = MIXED_CONTENT_RE.findall(body)
    if matches:
        return Finding("mixed_content", "No mixed content", "fail",
                        f"Found {len(matches)} http:// resource reference(s) on an https page.")
    return Finding("mixed_content", "No mixed content", "pass", "No plain-http resource references found.")


def _check_cookies(resp):
    if not resp.cookies:
        return Finding("cookie_flags", "Cookie security flags", "info", "No cookies set on this response.")
    issues = []
    for cookie in resp.cookies:
        flags = []
        if not cookie.secure:
            flags.append("missing Secure")
        if not cookie.has_nonstandard_attr("HttpOnly"):
            flags.append("missing HttpOnly")
        if not cookie.get_nonstandard_attr("SameSite"):
            flags.append("missing SameSite")
        if flags:
            issues.append(f"{cookie.name}: {', '.join(flags)}")
    if issues:
        return Finding("cookie_flags", "Cookie security flags", "warn", "; ".join(issues))
    return Finding("cookie_flags", "Cookie security flags", "pass", "All cookies set Secure/HttpOnly/SameSite.")


def _detect_software(headers, body):
    """Best-effort (product, version) pairs from the response we already
    fetched — no extra requests. Misses plenty; that's disclosed to the
    founder, not hidden."""
    found = []
    h = {k.lower(): v for k, v in headers.items()}

    for header_name in ("server", "x-powered-by"):
        value = h.get(header_name, "")
        m = re.match(r"([A-Za-z][A-Za-z0-9._-]*)/(\d+(?:\.\d+){1,3})", value)
        if m:
            found.append((m.group(1), m.group(2)))

    m = GENERATOR_META_RE.search(body)
    if m:
        content = m.group(1).decode(errors="replace")
        gm = re.match(r"([A-Za-z][A-Za-z0-9 ._-]*?)\s+(\d+(?:\.\d+){1,3})", content)
        if gm:
            found.append((gm.group(1).strip(), gm.group(2)))

    jm = JQUERY_VERSION_RE.search(body)
    if jm:
        found.append(("jQuery", jm.group(1).decode()))

    # De-dupe while preserving order.
    seen = set()
    unique = []
    for product, version in found:
        key = (product.lower(), version)
        if key not in seen:
            seen.add(key)
            unique.append((product, version))
    return unique


def _lookup_cves(product, version):
    """Queries the public NVD database for a product+version. Best-effort:
    keyword search, not exact CPE matching, so results can be noisy — the
    founder sees the real CVE description and judges relevance themselves.
    Any NVD-side failure (timeout, rate limit, outage) becomes an 'info'
    finding, never a hard scan failure."""
    try:
        resp = requests.get(
            NVD_API_URL,
            params={"keywordSearch": f"{product} {version}", "resultsPerPage": MAX_CVES_PER_PRODUCT},
            headers={"User-Agent": USER_AGENT},
            timeout=NVD_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        return None, str(exc)

    cves = []
    for item in data.get("vulnerabilities", [])[:MAX_CVES_PER_PRODUCT]:
        cve = item.get("cve", {})
        cve_id = cve.get("id", "?")
        descriptions = cve.get("descriptions", [])
        summary = next((d["value"] for d in descriptions if d.get("lang") == "en"), "")
        cves.append((cve_id, summary))
    return cves, None


def _check_known_vulnerabilities(headers, body):
    products = _detect_software(headers, body)
    if not products:
        return [Finding(
            "cve_scan", "Known-CVE check", "info",
            "No specific software/version could be identified from the response — nothing to check against CVE records.",
            category="deep",
        )]

    findings = []
    for product, version in products:
        cves, error = _lookup_cves(product, version)
        label = f"Known CVEs for {product} {version}"
        if error is not None:
            findings.append(Finding(f"cve_{product.lower()}", label, "info",
                                     f"Could not check ({error}) — try again later.", category="deep"))
        elif not cves:
            findings.append(Finding(f"cve_{product.lower()}", label, "pass",
                                     "No matching entries found in the public NVD database (best-effort keyword search, not exhaustive).",
                                     category="deep"))
        else:
            detail = " | ".join(f"{cid}: {summary[:160]}" for cid, summary in cves)
            findings.append(Finding(f"cve_{product.lower()}", label, "warn",
                                     f"Possible matches — verify relevance yourself: {detail}", category="deep"))
    return findings


def _check_dns_security(hostname):
    findings = []

    try:
        answers = dns.resolver.resolve(hostname, "TXT", lifetime=5)
        txt_records = ["".join(s.decode(errors="replace") for s in r.strings) for r in answers]
        spf_found = any(t.lower().startswith("v=spf1") for t in txt_records)
    except Exception:
        spf_found = False
    findings.append(Finding(
        "dns_spf", "SPF record (email spoofing protection)", "pass" if spf_found else "warn",
        "Found." if spf_found else "No SPF TXT record — makes it easier to spoof emails 'from' this domain.",
        category="deep",
    ))

    try:
        answers = dns.resolver.resolve(f"_dmarc.{hostname}", "TXT", lifetime=5)
        txt_records = ["".join(s.decode(errors="replace") for s in r.strings) for r in answers]
        dmarc_found = any(t.lower().startswith("v=dmarc1") for t in txt_records)
    except Exception:
        dmarc_found = False
    findings.append(Finding(
        "dns_dmarc", "DMARC record (email spoofing protection)", "pass" if dmarc_found else "warn",
        "Found." if dmarc_found else "No DMARC record at _dmarc.<domain> — recommended alongside SPF.",
        category="deep",
    ))

    return findings


def _check_exposed_files(final_url):
    parsed = urlparse(final_url)
    origin = f"{parsed.scheme}://{parsed.hostname}" + (f":{parsed.port}" if parsed.port else "")
    findings = []

    for path, marker in SENSITIVE_PATHS:
        target = origin + path
        exposed = False
        try:
            _validate_url(target)  # same host as the already-validated target; defense in depth
            resp = requests.get(
                target, headers={"User-Agent": USER_AGENT}, timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
                allow_redirects=False, stream=True,
            )
            chunk = next(iter(resp.iter_content(chunk_size=2048)), b"")
            resp.close()
            exposed = resp.status_code == 200 and (marker is None or marker in chunk)
        except Exception:
            exposed = False

        finding_id = "exposed_" + path.strip("/").replace("/", "_").replace(".", "_")
        findings.append(Finding(
            finding_id, f"{path} not publicly exposed", "fail" if exposed else "pass",
            f"Responded 200 with plausible content — this can leak sensitive data. Remove or block public access." if exposed
            else "Not exposed (404/blocked, or content didn't match).",
            category="deep",
        ))

    return findings


def scan_url(url, deep=False):
    """Run the full basic-hygiene scan against `url` and return a ScanResult.
    Raises ScanError if the target can't be safely or successfully fetched
    at all (caller should record that as a failed scan, not crash).

    deep=True additionally runs the "known vulnerabilities" report (CVE
    lookups, DNS security records, exposed-file checks) — see the module
    docstring. Deep findings are informational only: they never affect
    score/badge_level, and a failure in any one of them (e.g. NVD being
    unreachable) never fails the whole scan."""
    resp, body, final_url = _safe_get(url)
    try:
        findings = [_check_https(url, final_url), _check_tls_cert(final_url)]
        findings.extend(_check_headers(resp.headers))
        findings.append(_check_mixed_content(final_url, body))
        findings.append(_check_cookies(resp))

        if deep:
            findings.extend(_check_known_vulnerabilities(resp.headers, body))
            findings.extend(_check_dns_security(urlparse(final_url).hostname))
            findings.extend(_check_exposed_files(final_url))
    finally:
        resp.close()

    score = sum(POINTS.get(f.id, 0) for f in findings if f.status == "pass")
    badge_level = BadgeLevel.BASIC_VERIFIED if score >= PASS_THRESHOLD else BadgeLevel.NONE

    return ScanResult(badge_level=badge_level, score=score, max_score=MAX_SCORE, findings=findings)

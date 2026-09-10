"""
Tests for the opt-in "known vulnerabilities" deep scan — CVE lookups
(mocked NVD), DNS security records (mocked dns.resolver), and exposed-file
checks (mocked requests). See the "DEEP SCAN" section of
app/compliance/scanner.py's module docstring for the threat model and why
port scanning is deliberately excluded. Network-free by design, same as
tests/test_compliance_scan.py.
"""

import socket
from unittest.mock import MagicMock, patch

import pytest

from app import create_app
from app.extensions import db
from app.compliance import scanner
from app.models import (
    User, UserRole, FounderProfile, ProfileStatus,
    Subscription, SubscriptionTier, SubscriptionStatus,
)


def _mock_public_dns():
    return patch.object(
        scanner.socket, "getaddrinfo",
        return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))],
    )


# --- _detect_software --------------------------------------------------

def test_detect_software_from_server_header():
    found = scanner._detect_software({"Server": "nginx/1.18.0"}, b"<html></html>")
    assert ("nginx", "1.18.0") in found


def test_detect_software_from_generator_meta():
    body = b'<meta name="generator" content="WordPress 5.8" />'
    found = scanner._detect_software({}, body)
    assert ("WordPress", "5.8") in found


def test_detect_software_from_jquery_filename():
    body = b'<script src="/js/jquery-3.4.1.min.js"></script>'
    found = scanner._detect_software({}, body)
    assert ("jQuery", "3.4.1") in found


def test_detect_software_dedupes():
    found = scanner._detect_software({"Server": "nginx/1.18.0", "X-Powered-By": "nginx/1.18.0"}, b"")
    assert found.count(("nginx", "1.18.0")) == 1


def test_detect_software_none_found():
    assert scanner._detect_software({}, b"<html>nothing here</html>") == []


# --- _lookup_cves / _check_known_vulnerabilities -----------------------

def test_lookup_cves_parses_nvd_response():
    fake_response = MagicMock()
    fake_response.json.return_value = {
        "vulnerabilities": [
            {"cve": {"id": "CVE-2021-1234", "descriptions": [{"lang": "en", "value": "Something bad."}]}},
        ]
    }
    with patch.object(scanner.requests, "get", return_value=fake_response):
        cves, error = scanner._lookup_cves("nginx", "1.18.0")
    assert error is None
    assert cves == [("CVE-2021-1234", "Something bad.")]


def test_lookup_cves_handles_nvd_failure_gracefully():
    with patch.object(scanner.requests, "get", side_effect=scanner.requests.exceptions.ConnectionError("down")):
        cves, error = scanner._lookup_cves("nginx", "1.18.0")
    assert cves is None
    assert error is not None


def test_check_known_vulnerabilities_no_software_detected():
    findings = scanner._check_known_vulnerabilities({}, b"<html></html>")
    assert len(findings) == 1
    assert findings[0].status == "info"
    assert findings[0].category == "deep"


def test_check_known_vulnerabilities_reports_matches_as_warn():
    fake_response = MagicMock()
    fake_response.json.return_value = {
        "vulnerabilities": [{"cve": {"id": "CVE-2021-1234", "descriptions": [{"lang": "en", "value": "Bad."}]}}]
    }
    with patch.object(scanner.requests, "get", return_value=fake_response):
        findings = scanner._check_known_vulnerabilities({"Server": "nginx/1.18.0"}, b"")
    assert any(f.status == "warn" and "CVE-2021-1234" in f.detail for f in findings)
    assert all(f.category == "deep" for f in findings)


# --- _check_dns_security -------------------------------------------------

def test_dns_security_detects_spf_and_dmarc():
    def fake_resolve(name, rtype, lifetime=5):
        record = MagicMock()
        if name.startswith("_dmarc"):
            record.strings = [b"v=DMARC1; p=none"]
        else:
            record.strings = [b"v=spf1 include:_spf.example.com ~all"]
        return [record]

    with patch.object(scanner.dns.resolver, "resolve", side_effect=fake_resolve):
        findings = scanner._check_dns_security("example.com")

    by_id = {f.id: f for f in findings}
    assert by_id["dns_spf"].status == "pass"
    assert by_id["dns_dmarc"].status == "pass"


def test_dns_security_warns_when_missing():
    with patch.object(scanner.dns.resolver, "resolve", side_effect=Exception("NXDOMAIN")):
        findings = scanner._check_dns_security("example.com")
    assert all(f.status == "warn" for f in findings)


# --- _check_exposed_files -------------------------------------------------

def test_exposed_files_flags_real_git_config():
    def fake_get(url, **kwargs):
        resp = MagicMock()
        if url.endswith("/.git/config"):
            resp.status_code = 200
            resp.iter_content.return_value = [b"[core]\nrepositoryformatversion = 0"]
        else:
            resp.status_code = 404
            resp.iter_content.return_value = [b""]
        return resp

    with _mock_public_dns(), patch.object(scanner.requests, "get", side_effect=fake_get):
        findings = scanner._check_exposed_files("https://example.com/")

    by_id = {f.id: f for f in findings}
    assert by_id["exposed__git_config"].status == "fail"
    assert by_id["exposed__env"].status == "pass"


def test_exposed_files_all_clean():
    def fake_get(url, **kwargs):
        resp = MagicMock()
        resp.status_code = 404
        resp.iter_content.return_value = [b""]
        return resp

    with _mock_public_dns(), patch.object(scanner.requests, "get", side_effect=fake_get):
        findings = scanner._check_exposed_files("https://example.com/")
    assert all(f.status == "pass" for f in findings)


# --- scan_url(deep=True) end-to-end orchestration -------------------------

def _mock_response(headers, body=b"<html></html>"):
    resp = MagicMock()
    resp.status_code = 200
    resp.headers = headers
    resp.cookies = []
    resp.iter_content.return_value = [body]
    return resp


def test_deep_scan_findings_do_not_affect_score():
    good_headers = {
        "Strict-Transport-Security": "max-age=63072000",
        "Content-Security-Policy": "default-src 'self'; frame-ancestors 'none'",
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
    }
    with _mock_public_dns(), \
         patch.object(scanner.requests, "get", return_value=_mock_response(good_headers)), \
         patch.object(scanner, "_check_tls_cert", return_value=scanner.Finding("tls_cert", "x", "pass", "mocked")), \
         patch.object(scanner.dns.resolver, "resolve", side_effect=Exception("skip")):
        shallow = scanner.scan_url("https://example.com/", deep=False)
        deep = scanner.scan_url("https://example.com/", deep=True)

    assert deep.score == shallow.score
    assert deep.badge_level == shallow.badge_level
    assert any(f.category == "deep" for f in deep.findings)
    assert not any(f.category == "deep" for f in shallow.findings)


# --- Routes: consent gate -------------------------------------------------

@pytest.fixture
def app():
    app = create_app("testing")
    with app.app_context():
        db.create_all()
    yield app
    with app.app_context():
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def _make_profile(app, tier_status=SubscriptionStatus.ACTIVE):
    with app.app_context():
        user = User(email="founder@example.com", role=UserRole.FOUNDER)
        user.set_password("password123")
        db.session.add(user)
        db.session.commit()

        profile = FounderProfile(
            user_id=user.id, slug="test-project", project_name="Test Project",
            external_url="https://example.com", status=ProfileStatus.PUBLISHED,
        )
        db.session.add(profile)
        db.session.flush()
        db.session.add(Subscription(
            founder_profile_id=profile.id, tier=SubscriptionTier.PRESENTATION, status=tier_status,
        ))
        db.session.commit()
        return profile.id


def _login(client):
    client.post("/auth/login", data={"email": "founder@example.com", "password": "password123"})


def test_consent_requires_active_subscription(app, client):
    _make_profile(app, tier_status=SubscriptionStatus.CANCELLED)
    _login(client)

    resp = client.post("/compliance/vuln-scan-consent", follow_redirects=True)
    assert resp.status_code == 200
    assert b"active subscription is required" in resp.data

    with app.app_context():
        assert FounderProfile.query.first().vuln_scan_consent_given_at is None


def test_consent_recorded_with_active_subscription(app, client):
    _make_profile(app, tier_status=SubscriptionStatus.TRIAL)
    _login(client)

    resp = client.post("/compliance/vuln-scan-consent", follow_redirects=True)
    assert resp.status_code == 200

    with app.app_context():
        assert FounderProfile.query.first().vuln_scan_consent_given_at is not None


def test_scan_runs_deep_only_after_consent(app, client):
    _make_profile(app, tier_status=SubscriptionStatus.TRIAL)
    _login(client)

    good_headers = {
        "Strict-Transport-Security": "max-age=63072000",
        "Content-Security-Policy": "default-src 'self'",
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
    }
    with _mock_public_dns(), \
         patch.object(scanner.requests, "get", return_value=_mock_response(good_headers)), \
         patch.object(scanner, "_check_tls_cert", return_value=scanner.Finding("tls_cert", "x", "pass", "mocked")), \
         patch.object(scanner.dns.resolver, "resolve", side_effect=Exception("skip")):
        client.post("/compliance/run-basic-scan")

    with app.app_context():
        profile = FounderProfile.query.first()
        scan = profile.latest_compliance_scan
        assert not any(f["category"] == "deep" for f in scan.findings)

    client.post("/compliance/vuln-scan-consent")

    with app.app_context():
        profile = FounderProfile.query.first()
        profile.latest_compliance_scan.scan_date = profile.latest_compliance_scan.scan_date.replace(year=2000)
        db.session.commit()  # bypass cooldown for the test

    with _mock_public_dns(), \
         patch.object(scanner.requests, "get", return_value=_mock_response(good_headers)), \
         patch.object(scanner, "_check_tls_cert", return_value=scanner.Finding("tls_cert", "x", "pass", "mocked")), \
         patch.object(scanner.dns.resolver, "resolve", side_effect=Exception("skip")):
        client.post("/compliance/run-basic-scan")

    with app.app_context():
        profile = FounderProfile.query.first()
        scan = profile.latest_compliance_scan
        assert any(f["category"] == "deep" for f in scan.findings)

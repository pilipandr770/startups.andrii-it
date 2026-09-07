"""
Tests for the compliance scanner (app/compliance/scanner.py).

These deliberately avoid hitting the real network — SSRF-guard checks are
pure (hostname/IP validation), and the HTTP-dependent checks are exercised
against mocked `requests` responses. See the module docstring in
scanner.py for the threat model this defends against.
"""

import socket
from unittest.mock import MagicMock, patch

import pytest

from app.compliance import scanner
from app.compliance.scanner import Finding, ScanError, scan_url


def _mock_public_dns():
    """example.com et al. are used as stand-ins for 'some public site' in
    these tests — mock DNS resolution so tests don't depend on real network
    access, without touching how localhost/IP-literal targets resolve
    (those need their real, network-free resolution to exercise the SSRF
    guard itself)."""
    return patch.object(
        scanner.socket, "getaddrinfo",
        return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))],
    )


# --- SSRF guards -------------------------------------------------------

@pytest.mark.parametrize("url", [
    "http://localhost/",
    "http://127.0.0.1/",
    "http://169.254.169.254/",  # cloud metadata endpoint
    "http://[::1]/",
    "http://10.0.0.5/",
    "http://192.168.1.1/",
])
def test_blocks_private_and_internal_targets(url):
    with pytest.raises(ScanError):
        scanner._validate_url(url)


@pytest.mark.parametrize("url", [
    "file:///etc/passwd",
    "ftp://example.com/",
    "gopher://example.com/",
])
def test_blocks_non_http_schemes(url):
    with pytest.raises(ScanError):
        scanner._validate_url(url)


def test_safe_get_rejects_redirect_to_internal_address():
    redirect_resp = MagicMock()
    redirect_resp.status_code = 302
    redirect_resp.headers = {"Location": "http://127.0.0.1/admin"}

    with _mock_public_dns(), patch.object(scanner.requests, "get", return_value=redirect_resp):
        with pytest.raises(ScanError):
            scanner._safe_get("https://example.com/")


def test_safe_get_gives_up_after_too_many_redirects():
    redirect_resp = MagicMock()
    redirect_resp.status_code = 302
    redirect_resp.headers = {"Location": "https://example.com/next"}

    with _mock_public_dns(), patch.object(scanner.requests, "get", return_value=redirect_resp):
        with pytest.raises(ScanError, match="Too many redirects"):
            scanner._safe_get("https://example.com/")


# --- Individual header/content checks -----------------------------------

def test_check_headers_all_present_pass():
    headers = {
        "Strict-Transport-Security": "max-age=63072000",
        "Content-Security-Policy": "default-src 'self'; frame-ancestors 'none'",
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
    }
    findings = scanner._check_headers(headers)
    by_id = {f.id: f for f in findings}
    assert by_id["strict-transport-security"].status == "pass"
    assert by_id["content-security-policy"].status == "pass"
    assert by_id["x-content-type-options"].status == "pass"
    assert by_id["referrer-policy"].status == "pass"
    assert by_id["frame_protection"].status == "pass"
    assert by_id["version_disclosure"].status == "pass"


def test_check_headers_missing_all_fail():
    findings = scanner._check_headers({})
    by_id = {f.id: f for f in findings}
    assert by_id["strict-transport-security"].status == "fail"
    assert by_id["content-security-policy"].status == "fail"
    assert by_id["frame_protection"].status == "warn"


def test_check_headers_flags_version_disclosure():
    findings = scanner._check_headers({"Server": "nginx/1.18.0", "X-Powered-By": "PHP/7.2"})
    by_id = {f.id: f for f in findings}
    assert by_id["version_disclosure"].status == "info"
    assert "nginx" in by_id["version_disclosure"].detail


def test_check_mixed_content_detects_http_resources():
    body = b'<html><img src="http://insecure.example.com/a.png"></html>'
    finding = scanner._check_mixed_content("https://example.com/", body)
    assert finding.status == "fail"


def test_check_mixed_content_clean_page():
    body = b'<html><img src="https://example.com/a.png"></html>'
    finding = scanner._check_mixed_content("https://example.com/", body)
    assert finding.status == "pass"


def test_check_mixed_content_skipped_on_http():
    finding = scanner._check_mixed_content("http://example.com/", b"<html></html>")
    assert finding.status == "info"


def test_check_cookies_flags_missing_flags():
    resp = MagicMock()
    cookie = MagicMock()
    cookie.name = "session"
    cookie.secure = False
    cookie.has_nonstandard_attr.return_value = False
    cookie.get_nonstandard_attr.return_value = None
    resp.cookies = [cookie]
    finding = scanner._check_cookies(resp)
    assert finding.status == "warn"
    assert "Secure" in finding.detail


def test_check_cookies_none_set():
    resp = MagicMock()
    resp.cookies = []
    finding = scanner._check_cookies(resp)
    assert finding.status == "info"


# --- End-to-end scan_url with a fully mocked fetch -----------------------

def _mock_response(headers, body=b"<html></html>"):
    resp = MagicMock()
    resp.status_code = 200
    resp.headers = headers
    resp.cookies = []
    resp.iter_content.return_value = [body]
    return resp


def test_scan_url_earns_basic_verified_with_good_headers():
    good_headers = {
        "Strict-Transport-Security": "max-age=63072000",
        "Content-Security-Policy": "default-src 'self'; frame-ancestors 'none'",
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
    }
    with _mock_public_dns(), \
         patch.object(scanner.requests, "get", return_value=_mock_response(good_headers)), \
         patch.object(scanner, "_check_tls_cert", return_value=Finding("tls_cert", "Valid TLS certificate", "pass", "mocked")):
        result = scan_url("https://example.com/")

    assert result.badge_level == "basic_verified"
    assert result.score >= scanner.PASS_THRESHOLD


def test_scan_url_no_badge_with_no_headers():
    with _mock_public_dns(), \
         patch.object(scanner.requests, "get", return_value=_mock_response({})), \
         patch.object(scanner, "_check_tls_cert", return_value=Finding("tls_cert", "Valid TLS certificate", "fail", "mocked")):
        result = scan_url("https://example.com/")

    assert result.badge_level == "none"
    assert result.score < scanner.PASS_THRESHOLD


def test_scan_url_propagates_scan_error_for_unreachable_host():
    with _mock_public_dns(), \
         patch.object(scanner.requests, "get", side_effect=scanner.requests.exceptions.ConnectionError("boom")):
        with pytest.raises(ScanError):
            scan_url("https://example.com/")

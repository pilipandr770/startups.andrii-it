"""
Tests for app/compliance/url_reputation.py — the malware/phishing link
check that protects marketplace VISITORS (as opposed to
tests/test_compliance_scan.py and test_deep_scan.py, which protect the
founder). Network-free by design: every HTTP call is mocked.
"""

from unittest.mock import MagicMock, patch

import pytest

from app import create_app
from app.compliance import url_reputation as ur


@pytest.fixture
def app():
    app = create_app("testing")
    with app.app_context():
        yield app


# --- _check_urlhaus --------------------------------------------------------

def test_urlhaus_flags_active_malware_host(app):
    fake_response = MagicMock()
    fake_response.json.return_value = {
        "query_status": "ok",
        "urls": [{"url_status": "online", "threat": "malware_download"}],
    }
    with patch.object(ur.requests, "post", return_value=fake_response):
        finding = ur._check_urlhaus("bad.example")
    assert finding.status == "flagged"
    assert "malware_download" in finding.detail


def test_urlhaus_clean_when_no_records(app):
    fake_response = MagicMock()
    fake_response.json.return_value = {"query_status": "no_results"}
    with patch.object(ur.requests, "post", return_value=fake_response):
        finding = ur._check_urlhaus("good.example")
    assert finding.status == "clean"


def test_urlhaus_unknown_on_network_failure(app):
    with patch.object(ur.requests, "post", side_effect=ur.requests.exceptions.ConnectionError("down")):
        finding = ur._check_urlhaus("example.com")
    assert finding.status == "unknown"


# --- _check_google_safe_browsing -------------------------------------------

def test_gsb_skipped_when_not_configured(app):
    with app.app_context():
        finding = ur._check_google_safe_browsing("https://example.com")
    assert finding.status == "unknown"
    assert "Not configured" in finding.detail


def test_gsb_flags_matches(app):
    app.config["GOOGLE_SAFE_BROWSING_API_KEY"] = "test-key"
    fake_response = MagicMock()
    fake_response.json.return_value = {"matches": [{"threatType": "SOCIAL_ENGINEERING"}]}
    fake_response.raise_for_status = lambda: None
    with app.app_context(), patch.object(ur.requests, "post", return_value=fake_response):
        finding = ur._check_google_safe_browsing("https://phishing.example")
    assert finding.status == "flagged"
    assert "SOCIAL_ENGINEERING" in finding.detail


def test_gsb_clean_when_no_matches(app):
    app.config["GOOGLE_SAFE_BROWSING_API_KEY"] = "test-key"
    fake_response = MagicMock()
    fake_response.json.return_value = {}
    fake_response.raise_for_status = lambda: None
    with app.app_context(), patch.object(ur.requests, "post", return_value=fake_response):
        finding = ur._check_google_safe_browsing("https://example.com")
    assert finding.status == "clean"


# --- _check_virustotal -------------------------------------------------

def test_virustotal_skipped_when_not_configured(app):
    with app.app_context():
        finding = ur._check_virustotal("https://example.com")
    assert finding.status == "unknown"
    assert "Not configured" in finding.detail


def test_virustotal_flags_malicious(app):
    app.config["VIRUSTOTAL_API_KEY"] = "test-key"
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.raise_for_status = lambda: None
    fake_response.json.return_value = {
        "data": {"attributes": {"last_analysis_stats": {"malicious": 3, "suspicious": 1, "harmless": 60}}}
    }
    with app.app_context(), patch.object(ur.requests, "get", return_value=fake_response):
        finding = ur._check_virustotal("https://malware.example")
    assert finding.status == "flagged"
    assert "3 engine" in finding.detail


def test_virustotal_unanalyzed_url_is_unknown(app):
    app.config["VIRUSTOTAL_API_KEY"] = "test-key"
    fake_response = MagicMock()
    fake_response.status_code = 404
    with app.app_context(), patch.object(ur.requests, "get", return_value=fake_response):
        finding = ur._check_virustotal("https://never-seen.example")
    assert finding.status == "unknown"


# --- check_url_reputation (orchestrator) ------------------------------------

def test_overall_flagged_if_any_source_flags(app):
    with app.app_context():
        with patch.object(ur, "_check_urlhaus", return_value=ur.ReputationFinding("URLhaus", "flagged", "bad")), \
             patch.object(ur, "_check_google_safe_browsing", return_value=ur.ReputationFinding("GSB", "unknown", "n/a")), \
             patch.object(ur, "_check_virustotal", return_value=ur.ReputationFinding("VT", "unknown", "n/a")):
            status, detail = ur.check_url_reputation("https://bad.example")
    assert status == "flagged"
    assert "URLhaus" in detail


def test_overall_clean_if_none_flag_and_one_is_clean(app):
    with app.app_context():
        with patch.object(ur, "_check_urlhaus", return_value=ur.ReputationFinding("URLhaus", "clean", "ok")), \
             patch.object(ur, "_check_google_safe_browsing", return_value=ur.ReputationFinding("GSB", "unknown", "n/a")), \
             patch.object(ur, "_check_virustotal", return_value=ur.ReputationFinding("VT", "unknown", "n/a")):
            status, detail = ur.check_url_reputation("https://good.example")
    assert status == "clean"


def test_overall_unknown_if_all_unknown(app):
    with app.app_context():
        with patch.object(ur, "_check_urlhaus", return_value=ur.ReputationFinding("URLhaus", "unknown", "n/a")), \
             patch.object(ur, "_check_google_safe_browsing", return_value=ur.ReputationFinding("GSB", "unknown", "n/a")), \
             patch.object(ur, "_check_virustotal", return_value=ur.ReputationFinding("VT", "unknown", "n/a")):
            status, detail = ur.check_url_reputation("https://example.com")
    assert status == "unknown"

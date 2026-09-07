"""
Runs the automated "basic verified" scan (app/compliance/scanner.py) against
a founder's own external_url and records the result.

This only ever produces BadgeLevel.BASIC_VERIFIED or leaves the profile at
BadgeLevel.NONE. The deeper "nis2_ready" / "full_audit" tiers require the
real nis2.store / BSI A5 engine and are granted manually (superadmin) until
that's wired in — see docs/STATE.md and docs/ROADMAP.md, Phase 2.

Legal note (see docs/ARCHITECTURE.md, "Compliance badge — legal wording"):
the badge must always be presented as "met criteria X as of date Y", never
as a general security guarantee.
"""

import json
import logging
from datetime import datetime

from app.extensions import db
from app.models import ComplianceScan, BadgeLevel
from app.compliance.scanner import scan_url, ScanError

logger = logging.getLogger(__name__)


def run_basic_scan(founder_profile):
    try:
        result = scan_url(founder_profile.external_url)
        badge_level = result.badge_level
        summary = result.summary
        score = result.score
        findings_json = json.dumps(result.findings_as_dicts())
    except ScanError as exc:
        logger.info("Compliance scan failed for profile %s: %s", founder_profile.id, exc)
        badge_level = BadgeLevel.NONE
        summary = f"Scan could not complete: {exc}"
        score = None
        findings_json = None

    scan = ComplianceScan(
        founder_profile_id=founder_profile.id,
        badge_level=badge_level,
        scan_date=datetime.utcnow(),
        summary=summary,
        score=score,
        findings_json=findings_json,
        requested_by_founder=True,
    )
    db.session.add(scan)
    db.session.commit()
    return scan

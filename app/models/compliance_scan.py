import json
from datetime import datetime
from app.extensions import db


class BadgeLevel:
    NONE = "none"
    BASIC_VERIFIED = "basic_verified"
    NIS2_READY = "nis2_ready"
    FULL_AUDIT = "full_audit"

    ALL = [NONE, BASIC_VERIFIED, NIS2_READY, FULL_AUDIT]

    LABELS = {
        NONE: "Not scanned",
        BASIC_VERIFIED: "Basic Verified",
        NIS2_READY: "NIS2-Ready",
        FULL_AUDIT: "Full Audit",
    }


class ComplianceScan(db.Model):
    """
    Result of a compliance/security scan run against a founder's external
    project. NOTE: the badge must never be presented as a security guarantee
    — only as "met criteria X as of date Y". See docs/ARCHITECTURE.md,
    "Compliance badge — legal wording".

    The actual scanning engine is NOT included in this skeleton — this is
    the integration point for your existing nis2.store / BSI A5 tooling.
    Wire it up in app/compliance/service.py.
    """

    __tablename__ = "compliance_scans"

    id = db.Column(db.Integer, primary_key=True)
    founder_profile_id = db.Column(
        db.Integer, db.ForeignKey("founder_profiles.id"), nullable=False
    )

    badge_level = db.Column(db.String(30), default=BadgeLevel.NONE)
    scan_date = db.Column(db.DateTime, default=datetime.utcnow)
    report_path = db.Column(db.String(500), nullable=True)
    summary = db.Column(db.Text, nullable=True)
    score = db.Column(db.Integer, nullable=True)
    # JSON-encoded list of {id, label, status, detail} — see
    # app/compliance/scanner.py::Finding. Kept as a plain Text column rather
    # than a separate table since findings are only ever read back whole,
    # for one scan at a time.
    findings_json = db.Column(db.Text, nullable=True)
    requested_by_founder = db.Column(db.Boolean, default=True)

    @property
    def findings(self):
        if not self.findings_json:
            return []
        return json.loads(self.findings_json)

    def __repr__(self):
        return f"<ComplianceScan {self.badge_level} for profile {self.founder_profile_id}>"

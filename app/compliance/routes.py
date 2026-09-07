from datetime import datetime, timedelta

from flask import redirect, url_for, flash
from flask_login import login_required, current_user

from app.compliance import bp
from app.compliance.service import run_basic_scan
from app.models import BadgeLevel

# Cheap abuse guard: a scan makes an outbound request on the founder's
# behalf, so cap how often one profile can trigger it.
RESCAN_COOLDOWN = timedelta(minutes=5)


@bp.route("/run-basic-scan", methods=["POST"])
@login_required
def request_basic_scan():
    profile = current_user.founder_profile
    if not profile:
        flash("Create your project profile first.", "warning")
        return redirect(url_for("founder.edit_profile"))

    last_scan = profile.latest_compliance_scan
    if last_scan:
        elapsed = datetime.utcnow() - last_scan.scan_date
        if elapsed < RESCAN_COOLDOWN:
            wait_minutes = int((RESCAN_COOLDOWN - elapsed).total_seconds() // 60) + 1
            flash(f"Please wait {wait_minutes} more minute(s) before re-scanning.", "warning")
            return redirect(url_for("founder.dashboard"))

    scan = run_basic_scan(profile)
    if scan.badge_level == BadgeLevel.BASIC_VERIFIED:
        flash(f"Scan complete — Basic Verified badge earned. {scan.summary}", "success")
    else:
        flash(f"Scan complete — badge not earned yet. {scan.summary}", "info")
    return redirect(url_for("founder.dashboard"))

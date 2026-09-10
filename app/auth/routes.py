from flask import render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user

from app.auth import bp
from app.auth.forms import RegisterForm, LoginForm, ChangePasswordForm, DeleteAccountForm
from app.extensions import db
from app.models import User, UserRole
from app.founder.routes import delete_profile_uploads


@bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("founder.dashboard"))

    form = RegisterForm()
    if form.validate_on_submit():
        if User.query.filter_by(email=form.email.data.lower().strip()).first():
            flash("An account with this email already exists.", "danger")
            return render_template("auth/register.html", form=form)

        user = User(
            email=form.email.data.lower().strip(),
            legal_entity_name=form.legal_entity_name.data.strip() or None,
            role=UserRole.FOUNDER,
        )
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()

        login_user(user)
        flash("Welcome! Let's set up your project listing.", "success")
        return redirect(url_for("founder.edit_profile"))

    return render_template("auth/register.html", form=form)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("founder.dashboard"))

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data.lower().strip()).first()
        if user is None or not user.check_password(form.password.data):
            flash("Invalid email or password.", "danger")
            return render_template("auth/login.html", form=form)

        login_user(user, remember=form.remember_me.data)
        next_page = request.args.get("next")
        if user.role == UserRole.SUPERADMIN:
            return redirect(next_page or url_for("superadmin.index"))
        if user.role == UserRole.ADMIN:
            return redirect(next_page or url_for("admin.queue"))
        return redirect(next_page or url_for("founder.dashboard"))

    return render_template("auth/login.html", form=form)


@bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("marketplace.home"))


@bp.route("/account", methods=["GET", "POST"])
@login_required
def account():
    form = ChangePasswordForm()
    if form.validate_on_submit():
        current_user.set_password(form.new_password.data)
        db.session.commit()
        flash("Password changed.", "success")
        return redirect(url_for("auth.account"))

    delete_form = DeleteAccountForm()
    return render_template("auth/account.html", form=form, delete_form=delete_form)


@bp.route("/account/delete", methods=["POST"])
@login_required
def delete_account():
    form = DeleteAccountForm()
    if not form.validate_on_submit():
        for error in form.password.errors:
            flash(error, "danger")
        return redirect(url_for("auth.account"))

    # Resolve to a concrete row and delete it BEFORE logout_user(): current_user
    # is a LocalProxy that re-evaluates against the session on every access,
    # so using it after logout_user() clears that session would silently
    # operate on an anonymous user instead of the one we meant to delete.
    user = User.query.get(current_user.id)
    if user.founder_profile:
        delete_profile_uploads(user.founder_profile)  # DB cascade won't touch the filesystem
    db.session.delete(user)  # cascades: profile, chatbot config, scans, subscription, donations
    db.session.commit()
    logout_user()
    flash("Your account and all associated data have been deleted.", "info")
    return redirect(url_for("marketplace.home"))

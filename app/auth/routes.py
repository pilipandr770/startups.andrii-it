from flask import render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user

from app.auth import bp
from app.auth.forms import RegisterForm, LoginForm
from app.extensions import db
from app.models import User, UserRole


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

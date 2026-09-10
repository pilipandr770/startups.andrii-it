from flask_login import current_user
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField
from wtforms.validators import DataRequired, Email, Length, EqualTo, ValidationError


class RegisterForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email()])
    legal_entity_name = StringField(
        "Legal entity name (required to receive donations via your own Stripe)",
        validators=[Length(max=255)],
    )
    password = PasswordField("Password", validators=[DataRequired(), Length(min=8)])
    confirm_password = PasswordField(
        "Confirm password", validators=[DataRequired(), EqualTo("password")]
    )


class LoginForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email()])
    password = PasswordField("Password", validators=[DataRequired()])
    remember_me = BooleanField("Remember me")


class ChangePasswordForm(FlaskForm):
    current_password = PasswordField("Current password", validators=[DataRequired()])
    new_password = PasswordField("New password", validators=[DataRequired(), Length(min=8)])
    confirm_new_password = PasswordField(
        "Confirm new password", validators=[DataRequired(), EqualTo("new_password")]
    )

    def validate_current_password(self, field):
        if not current_user.check_password(field.data):
            raise ValidationError("That's not your current password.")


class DeleteAccountForm(FlaskForm):
    """Re-entering the password is deliberate friction for an irreversible,
    cascading delete (profile, listing, donations log, everything) — not
    just a CSRF-token click."""

    password = PasswordField("Confirm your password to delete your account", validators=[DataRequired()])

    def validate_password(self, field):
        if not current_user.check_password(field.data):
            raise ValidationError("That's not your password.")

from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField
from wtforms.validators import DataRequired, Email, Length, EqualTo


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

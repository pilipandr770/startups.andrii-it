from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_babel import Babel
from flask_wtf import CSRFProtect

db = SQLAlchemy()
login_manager = LoginManager()
migrate = Migrate()
babel = Babel()
csrf = CSRFProtect()

login_manager.login_view = "auth.login"
login_manager.login_message_category = "info"

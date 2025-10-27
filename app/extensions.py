from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_mail import Mail
from flask_migrate import Migrate
from flask_wtf import CSRFProtect


db = SQLAlchemy()
login_manager = LoginManager()
mail = Mail()
migrate = Migrate()  # ← instance, not the class
csrf = CSRFProtect()



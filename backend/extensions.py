"""Shared Flask extension singletons.

Kept in their own module so models and blueprints can import them without
creating circular imports with the application factory in ``app.py``.
"""
from flask_bcrypt import Bcrypt
from flask_cors import CORS
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
bcrypt = Bcrypt()
login_manager = LoginManager()
cors = CORS()

import importlib
import logging
import os
import pkgutil
import rq

from flask import Flask, request, current_app
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_mail import Mail
from flask_moment import Moment
from flask_wtf.csrf import CSRFProtect
from logging.handlers import SMTPHandler, RotatingFileHandler
from pathlib import Path
from redis import Redis

from config import Config


db = SQLAlchemy()
migrate = Migrate()
login = LoginManager()
login.login_view = 'auth.login'
login.login_message = 'Please log in to access this page.'
mail = Mail()
moment = Moment()


def create_app(config_class=Config):
  app = Flask(__name__)
  app.config.from_object(config_class)

  db.init_app(app)
  migrate.init_app(app, db)
  login.init_app(app)
  mail.init_app(app)
  moment.init_app(app)
  csrf = CSRFProtect(app)
  app.redis = Redis.from_url(app.config['REDIS_URL'])
  app.task_queue = rq.Queue('framease-tasks', connection=app.redis)

  from app.errors import bp as errors_bp
  app.register_blueprint(errors_bp)

  from app.auth import bp as auth_bp
  app.register_blueprint(auth_bp, url_prefix='/auth')

  from app.main import bp as main_bp
  app.register_blueprint(main_bp)

  from app.cli import bp as cli_bp
  app.register_blueprint(cli_bp)

  from app.admin import bp as admin_bp
  app.register_blueprint(admin_bp, url_prefix='/admin')

  from app.api import bp as api_bp
  app.register_blueprint(api_bp, url_prefix='/api')

  if not app.debug and not app.testing:
    if app.config['MAIL_SERVER']:
      auth = None
      if app.config['MAIL_USERNAME'] or app.config['MAIL_PASSWORD']:
        auth = (app.config['MAIL_USERNAME'], app.config['MAIL_PASSWORD'])
      secure = None
      if app.config['MAIL_USE_TLS']:
        secure = ()
      mail_handler = SMTPHandler(
        mailhost=(app.config['MAIL_SERVER'], app.config['MAIL_PORT']),
        fromaddr=app.config['MAIL_SENDER'],
        toaddrs=app.config['ADMINS'], subject='Framease Failure',
        credentials=auth, secure=secure)
      mail_handler.setLevel(logging.ERROR)
      app.logger.addHandler(mail_handler)

    if app.config['LOG_TO_STDOUT']:
      stream_handler = logging.StreamHandler()
      stream_handler.setLevel(logging.INFO)
      app.logger.addHandler(stream_handler)
    else:
      if not os.path.exists('logs'):
        os.mkdir('logs')
      file_handler = RotatingFileHandler('logs/framease.log',
        maxBytes=10240, backupCount=10)
      file_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s '
        '[in %(pathname)s:%(lineno)d]'))
      file_handler.setLevel(logging.INFO)
      app.logger.addHandler(file_handler)

    app.logger.setLevel(logging.INFO)
    app.logger.info('Framease startup')

  return app


from app import models

import app.plugins as _plugins
import app.validation_models as _validation_models

BASE_DIR = Path(__file__).parent
PLUGIN_PATH = BASE_DIR / 'plugins'
VALIDATION_MODEL_PATH = BASE_DIR / 'validation_models'

def iter_namespace(ns_pkg):
  # Specifying the second argument (prefix) to iter_modules makes the
  # returned name an absolute name instead of a relative one. This allows
  # import_module to work without having to do additional modification to
  # the name.
  return pkgutil.iter_modules(ns_pkg.__path__, ns_pkg.__name__ + '.')

plugins = {
  name: importlib.import_module(name)
  for finder, name, ispkg
  in iter_namespace(_plugins)
}


validation_models = {
  name: importlib.import_module(name)
  for finger, name, ispkg
  in iter_namespace(_validation_models)
}

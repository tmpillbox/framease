import os

from dotenv import load_dotenv


basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'))


class Config:
  SECRET_KEY = os.environ.get('SECRET_KEY') or 'MONDAY TUESDAY WEDNESDAY THURSDAY FRIDAY SATURDAY SUNDAY MONDAY TUESDAY...'
  SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', '').replace(
    'postgres://', 'postgresql://') or \
    'sqlite:///' + os.path.join(basedir, 'app.db')
  LOG_TO_STDOUT = os.environ.get('LOG_TO_STDOUT')
  MAIL_SERVER = os.environ.get('MAIL_SERVER')
  MAIL_SENDER = os.environ.get('MAIL_SENDER')
  MAIL_PORT = int(os.environ.get('MAIL_PORT') or 25)
  MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS') is not None
  MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
  MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
  ADMINS = ['']
  REDIS_URL = os.environ.get('REDIS_URL') or 'redis://'

  DEFAULT_PAGE_SIZE = 25

  DEFAULT_SSH_PORT = 22
  DEFAULT_HTTPS_PORT = 443
  

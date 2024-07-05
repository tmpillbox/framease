import sqlalchemy as sa
import sqlalchemy.orm as so

from app import create_app, db, plugins
from app.models import User, Notification, Task, Device, DeviceValidation, TestSuite, TestCase, Comment, DeviceValidationModel

app = create_app()

with app.app_context():
    db.create_all()


@app.shell_context_processor
def make_shell_context():
  return {
    'sa': sa,
    'so': so,
    'db': db,
    'User': User,
    'Notification': Notification,
    'Task': Task,
    'Device': Device,
    'DeviceValidation': DeviceValidation,
    'DeviceValidationModel': DeviceValidationModel,
    'TestSuite': TestSuite,
    'TestCase': TestCase,
    'Comment': Comment,
    'plugins': plugins
  }

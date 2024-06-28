import sqlalchemy as sa

import json
import sys
import time

from flask import render_template
from rq import get_current_job

from app import create_app, db
from app.models import User, Device, Task
from app.email import send_email


def _set_task_progress(progress):
  job = get_current_job()
  if job:
    job.meta['progress'] = progress
    job.save_meta()
    task = db.session.get(Task, job.get_id())
    task.user.add_notification('task_progress', {'task_id': job.get_id(),
                                                 'progress': progress})
    if progress >= 100:
      task.complete = True
    db.session.commit()

def run_device_validation(user_id, device_validation_id):
  try:
    user = db.session.get(User, user_id)
    val_id = db.session.get(DeviceValidation, device_validation_id)
    _set_task_progress(100)
  except Exception:
    _set_task_progress(100)
    app.logger.error('Unhandled exception', exc_info=sys.exc_info())
  finally:
    _set_task_progress(100)


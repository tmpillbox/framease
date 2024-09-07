import sqlalchemy as sa

import json
import sys
import time

from flask import render_template, current_app
from rq import get_current_job

from app import create_app, db
from app.models import User, Device, Task, DeviceValidation
from app.email import send_email

app = create_app()
app.app_context().push()

def _set_task_progress(progress):
  job = get_current_job()
  if job:
    job.meta['progress'] = progress
    job.save_meta()
    task = db.session.get(Task, job.get_id())
    if progress >= 100:
      task.complete = True
    db.session.commit()


def run_validation(user_id, device_validation_id):
  try:
    validation = db.session.get(DeviceValidation, device_validation_id)
  except:
    _set_task_progress(100)
    return
  validation_data = json.loads(validation.data)
  if 'history' not in validation_data:
    validation_data['history'] = list()
  if 'results' in validation_data:
    validation_data['history'].append(validation_data['results'])
  results = dict()
  validation_data['results'] = results
  try:
    device = validation.device
    device_model_data = device.get_model_data()
    for suitecase in validation.suite.cases:
      seq = str(suitecase.sequence)
      case = suitecase.case
      result = case.run(json.dumps(device_model_data))
      print(repr(result))
      if result:
        result = result.toJSON()
        if seq not in results:
          results[seq] = result
        else:
          results[seq].update(result)
      #print(f'# DEBUG: seq <{seq}> result: {result} results: {results}')
    validation.data = json.dumps(validation_data)
  except Exception:
    _set_task_progress(100)
    app.logger.error('Unhandled exception', exc_info=sys.exc_info())
  finally:
    validation.running = False
    db.session.commit()
    _set_task_progress(100)


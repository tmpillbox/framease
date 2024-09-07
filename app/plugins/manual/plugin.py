import json
import re
import sys

from app.utils.result import Results, Result

NONE = Result.Status.NONE
PASS = Result.Status.PASS
FAIL = Result.Status.FAIL
WARN = Result.Status.WARN


plugin_name = 'manual'

usage = '''plugin: manual


'''

def parameters():
  return [
    ('list', 'manual_steps', 'str:description, manual_check:bool:True, manual_approve:bool:True'),
  ]

def requires():
  return [
  ]

def check(data):
  if isinstance(data, str):
    data = json.loads(data)
  result = Results()
  try:
    for step in data['parameters']['manual_checks']:
      manual_check = bool(step['manual_check']) if 'manual_check' in step else True
      if manual_check:
        manual_check = Result.Status.WARN
      else:
        manual_check = Result.Status.PASS
      manual_approve = bool(step['manual_approve']) if 'manual_approve' in step else True
      if manual_approve:
        manual_approve = Result.Status.WARN
      else:
        manual_approve = Result.Status.PASS
      description = '[MANUAL CHECK] ' + step['description']
      result += Result(description, manual_check, approval_status=manual_approve)
    return result
  except:
    print('Unhandled exception', sys.exc_info())    
  return result

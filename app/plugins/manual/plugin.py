import json
import re
import sys

plugin_name = 'manual'

usage = '''plugin: manual


'''

def parameters():
  return [
    ('list', 'manual_steps', 'str:description'),
  ]

def requires():
  return [
  ]

def check(data):
  if isinstance(data, str):
    data = json.loads(data)
  result = dict()
  try:
    for step in data['parameters']['manual_checks']:
      description = '[MANUAL CHECK] ' + step['description']
      result[description] = False
    return result
  except:
    print('Unhandled exception', sys.exc_info())    
  return result
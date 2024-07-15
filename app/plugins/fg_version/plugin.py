import json

from app.utils.result import Result

NONE = Result.Status.NONE
PASS = Result.Status.PASS
FAIL = Result.Status.FAIL


plugin_name = 'fg_version'

usage = '''plugin: fg_version


'''

def parameters():
  return [
    ('str', 'version')
  ]

def requires():
  return [
    ('json', 'fgt_cli_configuration')
  ]


def check(data):
  try:
    data = json.loads(data)
  except:
    pass
  description = f'Software Version is ' + data['parameters']['fw_version']
  try:
    conf = data['fgt_cli_configuration']
    if conf['fw_version'] == data['parameters']['fw_version']:
      return { description: Result(description, PASS) }
    else:
      return { description + f' ({conf["fw_version"]})': Result(description + f' ({conf["fw_version"]})', FAIL) }
  except:
    pass
  return { description: Result(description, FAIL) }

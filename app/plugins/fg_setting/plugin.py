import json
import re


plugin_name = 'fg_setting'

usage = '''plugin: fg_setting


'''

def parameters():
  return [
    ('list', 'setting_specs', 'config_path, setting, value[|value[|...]], or_empty:False, partial_match:False, description:<{config_path}:{setting}>'),
  ]

def requires():
  return [
    ('json', 'fgt_cli_configuration')
  ]

def validate_setting(context, key, value, or_empty=False, partial_match=False):
  if isinstance(value, list):
    for val in value:
      if validate_setting(context, key, val, or_empty=or_empty, partial_match=partial_match):
        return True
    return False
  if key in context:
    if context[key] == value or context[key].strip('"') == value:
      return True
    elif partial_match:
      return value in context[key]
    else:
      print(f'# DEBUG: context: {context}')
      print(f'# DEBUG: key: <{key}> value: <{value}>')
      return False
  else:
    return or_empty

pipe_escape_split = r'(?<!\\)\|'

def check(data):
  if isinstance(data, str):
    data = json.loads(data)
  result = dict()
  try:
    for spec in data['parameters']['setting_specs']:
      config_path = spec['config_path']
      setting = spec['setting']
      value = re.split(pipe_escape_split, spec['value'])
      or_empty = spec.get('or_empty', False)
      partial_match = spec.get('partial_match', False)
      description = spec.get('description', f'{config_path}:{setting}')
      context = data['fgt_cli_configuration']['hierarchy']
      for path in config_path:
        context = context[path]
      result[description] = validate_setting(context, setting, value, or_empty=or_empty, partial_match=partial_match)
    return result
  except:
    pass
  return False

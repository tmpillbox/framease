import json


plugin_name = 'fg_setting'

usage = '''plugin: fg_setting


'''

def parameters():
  return [
    ('list', 'setting_specs', 'config_path, setting, value, or_empty:False, partial_match:False, description:<{config_path}:{setting}>'),
  ]

def requires():
  return [
    ('json', 'fgt_cli_configuration')
  ]

def validate_setting(context, key, value, or_empty=False, partial_match=False):
  if key in context:
    if context[key] == value:
      return True
    elif partial_match:
      return value in context[key]
    else:
      print(f'# DEBUG: context: {context}')
      print(f'# DEBUG: key: <{key}> value: <{value}>')
      return False
  else:
    return or_empty

def check(data):
  if isinstance(data, str):
    data = json.loads(data)
  result = dict()
  try:
    for spec in data['parameters']['setting_spec']:
      config_path = spec['config_path']
      setting = spec['setting']
      value = spec['value']
      or_empty = spec['or_empty'] if 'or_empty' in spec else False
      partial_match = spec['partial_match'] if 'partial_match' in spec else False
      description = spec['description'] if 'description' in spec else f'{config_path}:{setting}'
      context = data['fgt_cli_configuration']['hierarchy']
      for path in config_path:
        context = context[path]
      result[description] = validate_setting(context, setting, value, or_empty=or_empty, partial_match=partial_match)
    return result
  except:
    pass
  return False
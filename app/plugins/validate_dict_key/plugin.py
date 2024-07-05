
plugin_name = 'validate_dict_key'

usage = '''plugin: validate_dict_key

requires: "key" - key value to looking in supplied data
requires: "value" - expected value for data[key]
requires: "data" - dict object containing data

successful if:
  data[key] == value

'''

def parameters():
  return [
    ('str', 'key'),
    ('obj', 'value')
  ]

def requires():
  return [
    ('json', 'dict'),
  ]


def check(data):
  if 'key' not in data or 'value' not in data or 'data' not in data:
    raise KeyError
  key, value = data['key'], data['value']
  if data['key'] not in data['data']:
    raise KeyError
  return data['data'][key] == value


import json
import re
import sys
import traceback

from app.utils.result import Results, Result

NONE = Result.Status.NONE
PASS = Result.Status.PASS
FAIL = Result.Status.FAIL


plugin_name = 'fg_each'

usage = '''plugin: fg_each


'''

def parameters():
  return [
     ('list', 'setting_specs', '<type:policy|addr|addr6|addrgrp|addr6grp|admin|tacuser|usergroup>, <select:all|id:<id>[|<id>[|...>]], setting, value[|value[|...]], or_empty:False, partial_match:False, fail_on_match:False, pass_on_match:False, pass_threshhold:<all|none|any|[0-9]+>, negate_match:False, description:<{type}{select}:{setting}>'),
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
      #print(f'# DEBUG: context: {context}')
      #print(f'# DEBUG: key: <{key}> value: <{value}>')
      return False
  else:
    return or_empty

def _check_match(spec, entry):
  return f'edit {spec}' == entry or f'edit "{spec}"' == entry

def check_match(spec, entry, negate=False):
  if negate:
    return not check_match(spec, entry, negate=False)
  if spec is True:
    return True
  for sp in spec:
    if _check_match(sp, entry):
      return True
  return False

pipe_escape_split = r'(?<!\\)\|'

def check(data):
  if isinstance(data, str):
    data = json.loads(data)
  result = Results()
  try:
    for spec in data['parameters']['setting_specs']:
      spec_type = spec['type']
      select = spec.get('select', 'all')
      setting = spec['setting']
      value = re.split(pipe_escape_split, spec['value'])
      or_empty = spec.get('or_empty', False)
      partial_match = spec.get('partial_match', False)
      fail_on_match = spec.get('fail_on_match', False)
      pass_on_match = spec.get('pass_on_match', False)
      pass_threshhold = spec.get('pass_threshhold', 'all')
      negate_match = spec.get('negate_match', False)
      description = spec.get('description', f'{spec_type}:{select}:{setting}')
      if spec_type == 'policy':
        context = data['fgt_cli_configuration']['hierarchy']['config firewall policy']
      elif spec_type == 'addr':
        context = data['fgt_cli_configuration']['hierarchy']['config firewall address']
      elif spec_type == 'addr6':
        context = data['fgt_cli_configuration']['hierarchy']['config firewall address6']
      elif spec_type == 'addrgrp':
        context = data['fgt_cli_configuration']['hierarchy']['config firewall addrgrp']
      elif spec_type == 'addr6grp':
        context = data['fgt_cli_configuration']['hierarchy']['config firewall addr6grp']
      elif spec_type == 'admin':
        context = data['fgt_cli_configuration']['hierarchy']['config system admin']
      elif spec_type == 'tacuser':
        context = data['fgt_cli_configuration']['hierarchy']['config user tacacs+']
      elif spec_type == 'usergroup':
        context = data['fgt_cli_configuration']['hierarchy']['config user group']
      else:
        result += Result(description + ' [ERROR: type]', FAIL)
        continue
      if select.startswith('id:'):
        match_entry = re.split(pipe_escape_split, select[3:])
      elif select == 'all' or select == 'any':
        match_entry = True
      else:
        result += Result(description + ' [ERROR: select]', FAIL)
        continue
      match_count = 0
      pass_count = 0
      fail_count = 0
      for entry, ctx in context.items():
        if check_match(match_entry, entry, negate=negate_match):
          matched = entry.split(' ', 1)[-1].strip('"')
          print(f'# DEBUG: fg_each: match: {matched} (match_entry: {match_entry}, negate_match: {negate_match})')
          print(f'# DEBUG:   description: {description}')
          match_count += 1
          if fail_on_match:
            result += Result(description + f' ({matched} found)', FAIL)
            fail_count += 1
          elif pass_on_match:
            result += Result(description + f' ({matched} found)', PASS)
            pass_count += 1
          else:
            res = validate_setting(ctx, setting, value, or_empty=or_empty, partial_match=partial_match)
            if res:
              pass_count += 1
            else:
              fail_count += 1
      if fail_on_match:
        result += Result(description + f' (user not found)', PASS)
      else:
        if pass_threshhold == 'all':
          result += (
            Result(description + f' ({pass_count} pass/{fail_count} fail/{match_count} matched)', PASS)
            if pass_count and not fail_count else
            Result(description + f' ({pass_count} pass/{fail_count} fail/{match_count} matched)', FAIL)
          )
        elif pass_threshhold == 'any':
          result += (
            Result(description + f' ({pass_count} pass/{fail_count} fail/{match_count} matched)', PASS)
            if pass_count else
            Result(description + f' ({pass_count} pass/{fail_count} fail/{match_count} matched)', FAIL)
          )
        elif pass_threshhold == 'none':
          result += (
            Result(description + f' ({fail_count} pass/{pass_count} fail/{match_count} matched)', PASS)
            if fail_count and not pass_count else
            Result(description + f' ({fail_count} pass/{pass_count} fail/{match_count} matched)', FAIL)
          )
        elif pass_threshhold.isdigit():
          pass_threshhold = int(pass_threshhold)
          if pass_threshhold > 0:
            result += (
              Result(description + f' ({pass_count} pass/{fail_count} fail/{match_count} matched)', PASS)
              if pass_count > pass_threshhold else
              Result(description + f' ({pass_count} pass/{fail_count} fail/{match_count} matched)', FAIL)
            )
          elif pass_threshhold == 0:
            result += (
              Result(description + f' ({fail_count} pass/{pass_count} fail/{match_count} matched)', PASS)
              if fail_count and not pass_count else
              Result(description + f' ({fail_count} pass/{pass_count} fail/{match_count} matched)', FAIL)
            )
          elif pass_threshhold < 0:
            result += (
              Result(description + f' ({fail_count} pass/{pass_count} fail/{match_count} matched)', PASS)
              if fail_count and not pass_count else
              Result(description + f' ({fail_count} pass/{pass_count} fail/{match_count} matched)', FAIL)
            )
    return result
  except:
    print("Exception in user code:")
    print("-"*60)
    traceback.print_exc(file=sys.stdout)
    print("-"*60)
  return result
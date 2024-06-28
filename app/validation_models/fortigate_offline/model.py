import json
import shlex

model_name = 'fortigate_offline'


usage = '''model: fortigate_offline

requires: "file"

provides: "fgt_cli_configuration"


'''

def requires():
  return [
    'file'
  ]

def provides():
  return [
    'fgt_cli_configuration',
  ]

cleanip_skus = [
    '1511-CLEANIP-STD-SO-FP',
    '1511-CLEANIP-ADV-SO-FP',
    '1511-CLEANIP-ENT-SO-FP',
    '1511-CLEANIP-BAS-100-FP',
    '1511-CLEANIP-BAS-100-FP-HA',
    '1511-CLEANIP-BAS-250-FP',
    '1511-CLEANIP-BAS-250-FP-HA',
    '1511-CLEANIP-BAS-1G-FP',
    '1511-CLEANIP-BAS-1G-FP-HA',
    '1511-CLEANIP-STD-100-FP',
    '1511-CLEANIP-STD-100-FP-HA',
    '1511-CLEANIP-STD-250-FP',
    '1511-CLEANIP-STD-250-FP-HA',
    '1511-CLEANIP-STD-1G-FP',
    '1511-CLEANIP-STD-1G-FP-HA',
    '1511-CLEANIP-STD-100-FV',
    '1511-CLEANIP-STD-250-FV',
    '1511-CLEANIP-STD-1000-FV',
    '1511-CLEANIP-ADV-100-FP',
    '1511-CLEANIP-ADV-100-FP-HA',
    '1511-CLEANIP-ADV-250-FP',
    '1511-CLEANIP-ADV-250-FP-HA',
    '1511-CLEANIP-ADV-1G-FP',
    '1511-CLEANIP-ADV-1G-FP-HA',
    '1511-CLEANIP-ADV-100-FV',
    '1511-CLEANIP-ADV-250-FV',
    '1511-CLEANIP-ADV-1G-FV',
    '1511-CLEANIP-ENT-100-FP',
    '1511-CLEANIP-ENT-100-FP-HA',
    '1511-CLEANIP-ENT-250-FP',
    '1511-CLEANIP-ENT-250-FP-HA',
    '1511-CLEANIP-ENT-1G-FP',
    '1511-CLEANIP-ENT-1G-FP-HA',
    '1511-CLEANIP-ENT-100-FV',
    '1511-CLEANIP-ENT-250-FV',
    '1511-CLEANIP-ENT-1G-FV'
]

def match_prefix(prefix, cli_cfg):
  for key in cli_cfg:
    if key.startswith(prefix):
      yield key, cli_cfg[key]
  yield from []

def get_context(contexts, hier):
  path = hier[::]
  if path:
    p, path = path[0], path[1:]
    if p not in contexts:
      contexts[p] = dict()
    return get_context(contexts[p], path)
  return contexts

def set_value(ctx, key, val):
  ctx[key] = value


def process(job, data):
  fgt_cli_configuration = dict()
  admin_accounts = dict()
  interfaces = dict()
  config_lines = dict()
  config_hier = dict()

  fgt_cli_configuration['admin_accounts'] = admin_accounts
  fgt_cli_configuration['interfaces'] = interfaces
  fgt_cli_configuration['config'] = config_lines
  fgt_cli_configuration['hierarchy'] = config_hier

  file = [ line for line in data['file'] ]


  quoted_newline = ''
  for line in file:
    if quoted_newline:
      line = f'{quoted_newline}\\n{line}'
    if line.count('"') % 2:
      quoted_newline = line
      continue
    else:
      quoted_newline = ""
      config_lines.append(line)
  if quoted_newline:
    config_lines.append(quoted_newline)

  hier = list()
  context = fgt_cli_configuration['hierarchy']
  fw_version = ''
  for line in config_lines:
    if not line:
      continue
    if line.startswith('#config-version'):
      fgt_cli_configuration['fw_version'] = line.split('-')[2]
    tokens = shlex.split(line, posix=False)
    act, params = tokens[0], tokens[1:]
    if act == 'end':
      hier.pop()
      context = get_context(config_hier, hier)
    elif act == 'next':
      hier.pop()
      context = get_context(config_hier, hier)
    elif act == 'config':
      hier.append(line.lstrip())
      context = get_context(config_hier, hier)
    elif act == 'edit':
      hier.append(line.lstrip())
      context = get_context(config_hier, hier)
    elif act == 'set':
      config_key = '|'.join(hier) + f'|{act} {params[0]}'
      config_value = ' '.join(params[1:])
      config_lines[config_key] = config_value
      set_value(context, params[0], config_value)
      fgt_cli_configuration['config'][config_key] = config_value

  for edit_intf, ctx in fgt_cli_configuration['hierarchy']['config system interface'].items():
    interface = shlex.split(edit_intf)[-1]
    fgt_cli_configuration['interfaces'][interface] = json.dumps(ctx)

  for edit_admin, ctx in fgt_cli_configuration['hierarchy']['config system admin'].items():
    username = shlex.split(edit_admin)[-1]
    fgt_cli_configuration['admin_accounts'][username] = json.dumps(ctx)

  return json.dumps(fgt_cli_configuration)


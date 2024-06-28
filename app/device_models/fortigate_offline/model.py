

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
    'fgt_cli_configuration'
  ]


def process(job, data):
  pass

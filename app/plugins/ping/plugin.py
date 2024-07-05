import subprocess


plugin_name = 'ping'


usage = '''plugin: ping

requires: "ip_address" - IP Address of host to ping

successful if:
  IP address is pingable using system's ping command

'''

def parameters():
  return []

def requires():
  return [
    ('ip', 'ip_address')
  ]


def check(data):
  if 'ip_address' not in data:
    raise KeyError
  status, result = sp.getstatusoutput(f"ping -c1 -w2 {data['ip_address']}")
  job.meta['progress'] = 100
  if status == 0:
    job.meta['status'] = True
  else:
    job.meta['status'] = False


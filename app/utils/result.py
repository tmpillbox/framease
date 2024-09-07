import json
from enum import IntEnum

class Results:
  @classmethod
  def fromJSON(cls, jobj):
    jobj = json.loads(jobj)
    instance = cls()
    for result in jobj['results']:
      instance.add(Result.fromJSON(result))
    return instance
    
  def __init__(self):
    self.results = list()

  def add(self, result):
    self.results.append(result)
    return self

  def __iadd__(self, result):
    if isinstance(result, Result):
      return self.add(result)
    raise ValueError
    return

  def __ior__(self, results):
    if isinstance(results, Results):
      for result in results.results:
        self.add(result)
      return self
    raise ValueError
    return self
  
  def toJSON(self):
    return json.dumps({
      'results': [ result.toJSON() for result in self.results ]
    })


class Result:
  class Status(IntEnum):
    NONE = 0
    PASS = 1
    FAIL = 2
    WARN = 3
  
  @classmethod
  def fromJSON(cls, jobj):
    jobj = json.loads(jobj)
    instance = cls(
      jobj['description'],
      jobj['validation_status'],
      approval_status=jobj['approval_status']
    )
    instance.details = json.loads(jobj['details'])
    return instance

  def __init__(self, description, validation_status, approval_status=None):
    self.description = description
    self.validation_status = None
    self.approval_status = None
    try:
      self.validation_status = validation_status
      if approval_status and approval_status in self.Status:
        self.approval_status = approval_status
      else:
        self.approval_status = Result.Status.NONE
    except:
      if self.validation_status is None:
        self.validation_status = Result.Status.NONE
      if self.approval_status is None:
        self.approval_status = Result.Status.NONE
    self.details = list()

  def add_detail(self, detail):
    if not isinstance(detail, str):
      detail = json.dumps(detail)
    self.details.append(detail)

  def toJSON(self):
    return json.dumps({
      'description': self.description,
      'validation_status': self.validation_status,
      'approval_status': self.approval_status,
      'details': json.dumps(self.details)
    })



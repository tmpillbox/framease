import json
from enum import Enum


class Result:
  class Status(Enum):
    NONE = 0
    PASS = 1
    FAIL = 2
    WARN = 3

  def __init__(self, description, validation_status, approval_status=None):
    self.description = description
    self.validation_status = validation_status
    if approval_status and approval_status in self.Status:
      self.approval_status = approval_status
    else:
      self.approval_status = Result.Status.NONE
    self.details = list()

  def add_detail(self, detail):
    if not isinstance(detail, str):
      detail = json.dumps(detail)
    self.details.append(detail)

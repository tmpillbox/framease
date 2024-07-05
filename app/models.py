from __future__ import annotations

import sqlalchemy as sa
import sqlalchemy.orm as so

import json
import secrets
import jwt
import redis
import rq
import pkgutil
import importlib

from datetime import datetime, timezone, timedelta
from hashlib import md5
from flask import current_app, url_for
from flask_login import UserMixin, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy.sql import false
from time import time
from typing import List, Optional

from app import db, login

from app import plugins as _plugins
from app import validation_models as _validation_models

def iter_namespace(ns_pkg):
  # Specifying the second argument (prefix) to iter_modules makes the
  # returned name an absolute name instead of a relative one. This allows
  # import_module to work without having to do additional modification to
  # the name.
  return pkgutil.iter_modules(ns_pkg.__path__, ns_pkg.__name__ + '.')


validation_models = {
  name: importlib.import_module(name)
  for finger, name, ispkg
  in iter_namespace(_validation_models)
}

plugins = {
  name: importlib.import_module(name)
  for finger, name, ispkg
  in iter_namespace(_plugins)
}


# mapping tables
UserRole = sa.Table(
  'user_role',
  db.metadata,
  sa.Column('user_id', sa.Integer, sa.ForeignKey('user.id'), primary_key=True),
  sa.Column('role_id', sa.Integer, sa.ForeignKey('role.id'), primary_key=True)
)

# SuiteCase = sa.Table(
#   'suite_case',
#   db.metadata,
#   sa.Column('suite_id', sa.Integer, sa.ForeignKey('test_suite.id'), primary_key=True),
#   sa.Column('case_id', sa.Integer, sa.ForeignKey('test_case.id'), primary_key=True),
#   sa.Column('sequence', sa.Integer, index=True),
# )


class Role(db.Model):
  id: so.Mapped[int] = so.mapped_column(primary_key=True)
  name: so.Mapped[str] = so.mapped_column(sa.String(255), nullable=False, unique=True)
  active: so.Mapped[bool] = so.mapped_column(sa.Boolean, server_default=sa.false())

  users: so.Mapped[List['User']] = so.relationship(secondary=UserRole, back_populates='roles')


class User(db.Model, UserMixin):
  id: so.Mapped[int] = so.mapped_column(primary_key=True)
  username: so.Mapped[str] = so.mapped_column(sa.String(128), index=True, unique=True)
  display_name: so.Mapped[str] = so.mapped_column(sa.String())
  email: so.Mapped[str] = so.mapped_column(sa.String(120), index=True, unique=True)
  password_hash: so.Mapped[Optional[str]] = so.mapped_column(sa.String(140))
  about_me: so.Mapped[Optional[str]] = so.mapped_column(sa.String())
  last_seen: so.Mapped[Optional[datetime]] = so.mapped_column(
    default=lambda: datetime.now(timezone.utc))
  page_size: so.Mapped[Optional[int]] = so.mapped_column(sa.Integer())
  admin: so.Mapped[bool] = so.mapped_column(sa.Boolean, server_default=sa.false())
  token: so.Mapped[Optional[str]] = so.mapped_column(sa.String(32), index=True, unique=True)
  token_expiration: so.Mapped[Optional[datetime]]
  notifications: so.WriteOnlyMapped['Notification'] = so.relationship(
    back_populates='user')
  tasks: so.WriteOnlyMapped['Task'] = so.relationship(back_populates='user')
  roles: so.Mapped[List['Role']] = so.relationship(secondary=UserRole, back_populates='users')

  comments: so.Mapped['Comment'] = so.relationship(back_populates='author')

  def __repr__(self):
    return f'<User: {self.username}>'

  def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)
    self.page_size = self.page_size if self.page_size else current_app.config['DEFAULT_PAGE_SIZE']

  def set_password(self, password):
    self.password_hash = generate_password_hash(password)

  def check_password(self, password):
    return check_password_hash(self.password_hash, password)

  def get_reset_password_token(self, expires_in=600):
    return jwt.encode(
      {'reset_password': self.id, 'exp': time() + expires_in},
      current_app.config['SECRET'], algorithm='HS256')

  @staticmethod
  def verify_reset_password_token(token):
    try:
      id = jwt.decode(token, current_app.config['SECRET KEY'],
        algorithms=['HS256'])['reset_password']
    except Exception:
      return
    return db.session.get(User, id)

  def add_notification(self, name, data):
    db.session.execute(self.notifications.delete().where(
      Notification.name == name))
    n = Notification(name=name, payload_json=json.dumps(data), user=self)
    db.session.add(n)
    return n

  def launch_task(self, name, description, *args, **kwargs):
    rq_job = current_app.task_queue.enqueue(f'app.tasks.{name}', self.id, *args, **kwargs)
    task = Task(id=rq_job.get_id(), name=name, description=description, user=self)
    db.session.add(task)
    return task

  def get_tasks_in_progress(self):
    query = self.tasks.select().where(Task.complete == False)
    return db.session.scalars(query)

  def get_task_in_progress(self, name):
    query = self.tasks.select().where(Task.name == name, Task.complete == False)
    return db.session.scalar(query)

  def to_dict(self, include_email=False):
    data = {
      'id': self.id,
      'username': self.username,
    }
    if include_email:
      data['email'] = self.email
    return data

  def from_dict(self, data, new_user=False):
    for field in ['username', 'email', 'about_me']:
      if field in data:
        setattr(self, field, data[field])
      if new_user and 'password' in data:
        self.set_password(data['password'])

  def get_token(self, expires_in=300):
    now = datetime.now(timezone.utc)
    if self.token and self.token_expiration.replace(
        tzinfo=timezone.utc) > now + timedelta(seconds=60):
      return self.token
    self.token = secrets.token_hex(16)
    self.token_expiration = now + timedelta(seconds=expires_in)
    db.session.add(self)
    return self.token

  def revoke_token(self):
    self.token_expiration = datetime.now(timezone.utc) - timedelta(seconds=1)

  @staticmethod
  def check_token(token):
    user = db.session.scalar(sa.select(User).where(User.token == token))
    if user is None or user.token_expiration.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
      return None
    return user

  def has_role(self, role):
    return role in self.roles

  def add_role(self, role):
    if not self.has_role(role):
      self.roles.append(role)

  def remove_role(self, role):
    if self.has_role(role):
      self.roles.remove(role)


@login.user_loader
def load_user(id):
  return db.session.get(User, int(id))


class Notification(db.Model):
  id: so.Mapped[int] = so.mapped_column(primary_key=True)
  name: so.Mapped[str] = so.mapped_column(sa.String(128), index=True)
  user_id: so.Mapped[int] = so.mapped_column(sa.ForeignKey(User.id), index=True)
  timestamp: so.Mapped[float] = so.mapped_column(index=True, default=time)
  payload_json: so.Mapped[str] = so.mapped_column(sa.Text())

  user: so.Mapped[User] = so.relationship(back_populates='notifications')

  def get_data(self):
    return json.loads(str(self.payload_json))


class Task(db.Model):
  id: so.Mapped[str] = so.mapped_column(sa.String(36), primary_key=True)
  name: so.Mapped[str] = so.mapped_column(sa.String(128), index=True)
  description: so.Mapped[Optional[str]] = so.mapped_column(sa.String(128))
  user_id: so.Mapped[int] = so.mapped_column(sa.ForeignKey(User.id))
  obj_id: so.Mapped[int] = so.mapped_column(sa.Integer)
  complete: so.Mapped[bool] = so.mapped_column(sa.Boolean, server_default=sa.false())

  user: so.Mapped[User] = so.relationship(back_populates='tasks')

  def get_rq_job(self):
    try:
      rq_job = rq.job.Job.fetch(self.id, connection=current_app.redis)
    except (redis.exceptions.RedisError, rq.exceptions.NoSuchJobError):
      return None
    return rq_job

  def get_progress(self):
    job = self.get_rq_job()
    return job.meta.get('progress', 0) if job is not None else 100


class Device(db.Model):
  id: so.Mapped[int] = so.mapped_column(primary_key=True)
  devicename: so.Mapped[str] = so.mapped_column(sa.String(), index=True)
  hostname: so.Mapped[str] = so.mapped_column(sa.String(), index=True)
  ssh_port: so.Mapped[int] = so.mapped_column(sa.Integer())
  https_port: so.Mapped[int] = so.mapped_column(sa.Integer())
  archived: so.Mapped[bool] = so.mapped_column(sa.Boolean, server_default=sa.false())

  validations: so.WriteOnlyMapped['DeviceValidation'] = so.relationship(back_populates='device')
  validation_models: so.Mapped[List['DeviceValidationModel']] = so.relationship(back_populates='device')

  def __repr__(self):
    return f'<Device {self.devicename}>'

  def __str__(self):
    return str(self.devicename)

  @property
  def files_path(self):
    device_path = current_app.config['UPLOAD_PATH'] / f'{self.id}'
    device_path.mkdir(parents=False, exist_ok=True)
    return device_path
  
  @property
  def files(self):
    return [ str(f) for f in self.files_path.glob('*') if f.is_file() ] 


  def get_compatible_suites(self):
    provs = set()
    compat = list()
    for dvm in self.validation_models:
      for prov in dvm.provides:
        provs.add(prov)
    suites = TestSuite.query.all()
    for suite in suites:
      if all(req in provs for req in suite.requirements):
        compat.append(suite)
    return compat

  def get_model_data(self):
    data = dict()
    for dvm in sorted(self.validation_models, key=lambda dvm: dvm.sequence):
      dvm.reqs = dvm.requirements
      json_data = dvm.process(json.dumps(data))
      for req_name, req_data in json.loads(json_data).items():
        data[req_name] = req_data
    return data


class DeviceValidationModel(db.Model):
  id: so.Mapped[int] = so.mapped_column(primary_key=True)
  device_id: so.Mapped[int] = so.mapped_column(sa.ForeignKey(Device.id), index=True)
  sequence: so.Mapped[int] = so.mapped_column(sa.Integer(), index=True, default=0)
  validation_model: so.Mapped[str] = so.mapped_column(sa.String())
  validation_model_data: so.Mapped[str] = so.mapped_column(sa.Text(), nullable=True)

  device: so.Mapped[Device] = so.relationship(back_populates='validation_models')

  def __repr__(self):
    return f'<DeviceValidationModel: {self.device.devicename}, {self.validation_model}, {self.validation_model_data}>'

  @property
  def is_configured(self):
    try:
      data = json.loads(self.validation_model_data)
    except:
      self.initialize_data()
      data = json.loads(self.validation_model_data)
    for req_type, req_name in self.requirements:
      if data[req_name] is None:
        return False
    return True

  @classmethod
  def next_sequence(cls, deviceid):
    dvms = DeviceValidationModel.query.where(DeviceValidationModel.device_id == deviceid).all()
    return max([ dvm.sequence for dvm in dvms ] + [0]) + 1

  @property
  def requirements(self):
    if self.validation_model in validation_models:
      return validation_models[self.validation_model].requires()
    None

  @property
  def provides(self):
    if self.validation_model in validation_models:
      return validation_models[self.validation_model].provides()
  

  def show_requirement(self, req_name):
    data = self.get_data()
    if req_name in data:
      return data[req_name]
    return '<not configured>'

  def initialize_data(self):
    data = dict()
    try:
      for req_type, req_name in self.requirements:
        data[req_name] = None
        data[f'type:{req_name}'] = req_type
    finally:
      self.validation_model_data = json.dumps(data)

  def configure_requirement(self, req_name, value):
    json_raw = self.validation_model_data
    try:
      data = json.loads(json_raw)
    except:
      data = dict()
    data[req_name] = value
    self.validation_model_data = json.dumps(data)
    db.session.commit()

  def get_data(self):
    try:
      data = json.loads(self.validation_model_data)
    except:
      data = dict()
    return data

  def process(self, data):
    data = json.loads(data)
    local_data = self.get_data()
    data.update(local_data)
    data_updates = dict()
    for key, value in data.items():
      if key.startswith('type:') and value == 'file':
        req_name = key.split(':', 1)[-1]
        req_name = key.split(':', 1)[-1]
        if f'filedata:{req_name}' not in data:
          fname = data[req_name]
          with open(fname, 'r') as f:
            data_updates[f'filedata:{req_name}'] = f.readlines()
    if data_updates:
      data.update(data_updates)
    if self.validation_model in validation_models:
      for req_name, req_data in validation_models[self.validation_model].process(json.dumps(data)):
        data[req_name] = req_data
    return json.dumps(data)


class TestSuite(db.Model):
  id: so.Mapped[int] = so.mapped_column(primary_key=True)
  name: so.Mapped[str] = so.mapped_column(sa.String(80), index=True)
  version: so.Mapped[str] = so.mapped_column(sa.String(12), nullable=True)
  archived: so.Mapped[bool] = so.mapped_column(sa.Boolean, server_default=sa.false())
  final: so.Mapped[bool] = so.mapped_column(sa.Boolean, server_default=sa.false())

  validations: so.WriteOnlyMapped['DeviceValidation'] = so.relationship(back_populates='suite')
  cases: so.Mapped[List['SuiteCase']] = so.relationship('SuiteCase', primaryjoin='TestSuite.id == SuiteCase.suite_id')

  def __repr__(self):
    return f'<TestSuite({self.id}, {self.name}, {self.version})>'

  def __str__(self):
    return f'{self.name} ({self.version})'

  def add_case(self, caseid, sequence):
    self.cases.append(SuiteCase(self.id, caseid, sequence))

  @property
  def requirements(self):
    reqs = set()
    for suitecase in self.cases:
      for req in suitecase.case.requirements:
        reqs.add(req)
    return list(reqs)

  def get_cases_in_order(self):
    return sorted(self.cases, key=lambda c: c.sequence)


class DeviceValidation(db.Model):
  id: so.Mapped[int] = so.mapped_column(primary_key=True)
  device_id: so.Mapped[int] = so.mapped_column(sa.ForeignKey(Device.id), index=True)
  suite_id: so.Mapped[int] = so.mapped_column(sa.ForeignKey(TestSuite.id), index=True)
  name: so.Mapped[str] = so.mapped_column(sa.String())
  data: so.Mapped[str] = so.mapped_column(sa.Text())
  timestamp: so.Mapped[float] = so.mapped_column(index=True, default=time)
  archived: so.Mapped[bool] = so.mapped_column(sa.Boolean, server_default=sa.false())
  submitted: so.Mapped[bool] = so.mapped_column(sa.Boolean, server_default=sa.false())
  approved: so.Mapped[bool] = so.mapped_column(sa.Boolean, server_default=sa.false())
  final: so.Mapped[bool] = so.mapped_column(sa.Boolean, server_default=sa.false())
  running: so.Mapped[bool] = so.mapped_column(sa.Boolean, server_default=sa.false())

  comments: so.Mapped[List['Comment']] = so.relationship(back_populates='device_validation')
  device: so.Mapped['Device'] = so.relationship(back_populates='validations')
  suite: so.Mapped['TestSuite'] = so.relationship(back_populates='validations')

  @staticmethod
  def get_by_id(id):
    return DeviceValidation.query.where(DeviceValidation.id == id).first()

  def get_data(self):
    try:
      data = json.loads(self.data)
    except:
      data = dict()
    return data

  def num_suitecase_comments(self, sequence):
    return sum([ 1 for comment in self.comments if comment.sequence == sequence ])

  def sequence_status(self, sequence):
    data = self.get_data()
    if sequence in data:
      return data[sequence]
    if str(sequence) in data:
      return data[str(sequence)]
    return 'No Data'

  def row_status(self, sequence):
    data = self.get_data()
    if sequence in data:
      statuses = data[sequence]
    elif str(sequence) in data:
      statuses = data[str(sequence)]
    else:
      return 'no data'
    statuses = [ v for v in statuses.values() ]
    if all(statuses):
      return 'success'
    if not any(statuses):
      return 'failure'
    else:
      return 'incomplete'


  @property
  def has_secrets(self):
    for key, val in self.device.get_model_data():
      if val == 'secret':
        return True
    return False

  def run(self, user):
    rq_job = current_app.task_queue.enqueue(f'app.tasks.run_validation', user.id, self.id)
    task = Task(id=rq_job.get_id(), name='run_validation', user=user, obj_id=self.id)
    self.running = True
    db.session.add(task)
    db.session.commit()


class TestCase(db.Model):
  id: so.Mapped[int] = so.mapped_column(primary_key=True)
  name: so.Mapped[str] = so.mapped_column(sa.String(80), index=True)
  version: so.Mapped[str] = so.mapped_column(sa.String(12), nullable=True)
  description: so.Mapped[str] = so.mapped_column(sa.Text, nullable=True)
  function: so.Mapped[str] = so.mapped_column(sa.String(), nullable=True)
  data: so.Mapped[str] = so.mapped_column(sa.Text(), nullable=True)
  approver_role_id: so.Mapped[int] = so.mapped_column(sa.ForeignKey(Role.id), nullable=True)
  archived: so.Mapped[bool] = so.mapped_column(sa.Boolean, server_default=sa.false())

  suites: so.Mapped[List['SuiteCase']] = so.relationship('SuiteCase', primaryjoin='TestCase.id == SuiteCase.case_id')

  approver_role: so.Mapped[Role] = so.relationship(Role, primaryjoin='TestCase.approver_role_id == Role.id')

  def __repr__(self):
    return f'<TestCase({self.id}, {self.fucnction}, {self.data})>'

  @property
  def requirements(self):
    if self.function in plugins:
      return plugins[self.function].requires()
    None

  def get_data(self):
    try:
      data = json.loads(self.data)
    except:
      data = dict()
    return data

  def __str__(self):
    data = self.get_data()
    if 'description' in data:
      return data['description']
    return f'{self.name} ({self.version})'

  def run(self, data):
    data = json.loads(data)
    data['parameters'] = self.get_data()
    data_updates = dict()
    for key, value in data.items():
      if key.startswith('type:') and value == 'file':
        req_name = key.split(':', 1)[-1]
        if f'filedata:{req_name}' not in data:
          fname = data[req_name]
          with open(fname, 'r') as f:
            data_updates[f'filedata:{req_name}'] = f.readlines()
    if data_updates:
      data.update(data_updates)
    data_updates = dict()
    for key, value in data['parameters'].items():
      if key.startswith('type:') and value == 'file':
        req_name = key.split(':', 1)[-1]
        if f'filedata:{req_name}' not in data['parameters']:
          fname = data[req_name]
          with open(fname, 'r') as f:
            data_updates[f'filedata:{req_name}'] = f.readlines()
    if data_updates:
      data['parameters'].update(data_updates)
    if self.function in plugins:
      #for req_name, req_data in validation_models[self.validation_model].process(data):
      return plugins[self.function].check(json.dumps(data))

class Comment(db.Model):
  id: so.Mapped[int] = so.mapped_column(primary_key=True)
  body: so.Mapped[str] = so.mapped_column(sa.Text, nullable=True)
  user_id: so.Mapped[int] = so.mapped_column(sa.ForeignKey(User.id), index=True)
  validation_id: so.Mapped[int] = so.mapped_column(sa.ForeignKey(DeviceValidation.id), index=True)
  timestamp: so.Mapped[datetime] = so.mapped_column(
      index=True, default=lambda: datetime.now(timezone.utc))
  sequence: so.Mapped[int] = so.mapped_column(sa.Integer(), index=True)
  deleted: so.Mapped[bool] = so.mapped_column(sa.Boolean, server_default=sa.false())
  is_override: so.Mapped[bool] = so.mapped_column(sa.Boolean, server_default=sa.false())
  force_failure: so.Mapped[bool] = so.mapped_column(sa.Boolean, server_default=sa.false())

  device_validation: so.Mapped[DeviceValidation] = so.relationship(back_populates='comments')
  author: so.Mapped[User] = so.relationship(back_populates='comments')


# SuiteCase = sa.Table(
#   'suite_case',
#   db.metadata,
#   sa.Column('suite_id', sa.Integer, sa.ForeignKey('test_suite.id'), primary_key=True),
#   sa.Column('case_id', sa.Integer, sa.ForeignKey('test_case.id'), primary_key=True),
#   sa.Column('sequence', sa.Integer, index=True),
# )


class SuiteCase(db.Model):
  id: so.Mapped[int] = so.mapped_column(sa.Integer, primary_key=True, autoincrement=True)
  suite_id: so.Mapped[int] = so.mapped_column(sa.ForeignKey(TestSuite.id), index=True)
  case_id: so.Mapped[int] = so.mapped_column(sa.ForeignKey(TestCase.id), index=True)
  sequence: so.Mapped[int] = so.mapped_column(sa.Integer, index=True)

  suite: so.Mapped[TestSuite] = so.relationship(TestSuite, primaryjoin='SuiteCase.suite_id == TestSuite.id', back_populates='cases')
  case: so.Mapped[TestCase] = so.relationship(TestCase, primaryjoin='SuiteCase.case_id == TestCase.id', back_populates='suites')

  def __init__(self, suite_id, case_id, sequence, *args, **kwargs):
    super().__init__(*args, **kwargs)
    self.suite_id = suite_id
    self.case_id = case_id
    self.sequence = sequence

  @property
  def name(self):
    return str(self.case)

  @property
  def description(self):
    return self.case.description
  

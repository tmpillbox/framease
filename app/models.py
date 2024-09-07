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
import traceback

from datetime import datetime, timezone, timedelta
from hashlib import md5
from flask import current_app, flash, url_for, jsonify
from flask_login import UserMixin, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy.sql import false
from time import time
from typing import List, Optional

from app import db, login

from app import plugins as _plugins
from app import validation_models as _validation_models
from app.utils.result import Results, Result

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
  __table_args__ = (
    db.UniqueConstraint('name', 'version', name='_name_version_uc'),
  )

  validations: so.WriteOnlyMapped['DeviceValidation'] = so.relationship(back_populates='suite', passive_deletes=True)
  cases: so.Mapped[List['SuiteCase']] = so.relationship('SuiteCase', primaryjoin='TestSuite.id == SuiteCase.suite_id')

  def __repr__(self):
    return f'<TestSuite({self.id}, {self.name}, {self.version})>'

  def __str__(self):
    return f'{self.name} ({self.version})'

  @property
  def is_locked(self):
    return False
    return self.final or bool(list(db.session.scalars(self.validations.select())))
  
  def to_dict(self):
    return {
      'id': self.id,
      'name': self.name,
      'version': self.version,
      'archived': self.archived,
      'final': self.final,
      'cases': [
        { 'id': suitecase.id, 'sequence': suitecase.sequence, 'case': suitecase.case.to_dict() }
        for suitecase in self.cases
      ]
    }

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

  @classmethod
  def get_by_name_version(cls, name, version):
    res = TestSuite.query.where(TestSuite.name == name and TestSuite.version == version).first()
    if res.name == name and res.version == version:
      return res
    return None

  @classmethod
  def create_or_update_from_dict(cls, data):
    report_data = list()
    suite = None
    if 'id' in data:
      suite = cls.get_by_id(data['id'])
      if suite is not None:
        report_data.append( { 'h1': 'Success', 'detail': f'Found Test Suite by id: {data["id"]}: {str(suite)}'})
      elif 'name' in data and 'version' in data:
        suite = cls.get_by_name_version(data['name'], data['version'])
        if suite is not None:
          report_data.append( { 'h1': 'Error', 'warning': f'Attempt to create new Test Suite (id={data["id"]}) with existing name/version: {data["name"]} ({data["version"]})'})
          return report_data
        else:
          suite = cls(id=data['id'], name=data['name'], version=data['version'], archived=False, final=False)
          db.session.add(suite)
          db.session.commit()
          report_data.append( { 'h1': 'Success', 'detail': f'Create new Test Suite: {str(suite)}'})
    elif 'name' in data and 'version' in data:
      suite = cls.get_by_name_version(data['name'], data['version'])
      if suite is not None:
        report_data.append( { 'h1': 'Success', 'detail': f'Found Test Suite by name/version: {str(suite)}'})
      else:
        suite = cls(name=data['name'], version=data['version'], archived=False, final=False)
        db.session.add(suite)
        db.session.commit()
        report_data.append( { 'h1': 'Success', 'detail': f'Create new Test Suite: {str(suite)}'})
    if suite is None:
      report_data.append( { 'h1': 'Error', 'warning': 'Unable to find or import Test Suite.'} )
      return report_data
    
    # with db.session.begin_nested():
    #   import_report = list()
    #   if 'id' in suite_data:
    #     with db.session.begin_nest():
    #     # Try to update existing suite
    #     suite = db.first_or_404(sa.select(TestSuite).where(TestSuite.id == suite_data['id']))
    #     if suite.is_locked:
    #       flash('Unable to update Test Suite that is in use or marked final.')
    #       return redirect(url_for('admin.suites'))
    #     try:
    #       suite.import_update(suite_data)
    #       db.session.commit()
    #       return redirect(url_for('admin.suite', suiteid=suite.id))
    #     except:
    #       print("Exception in import:")
    #       print("-"*60)
    #       traceback.print_exc(file=sys.stdout)
    #       print("-"*60)
    #       flash(f'Invalid Data (Update by id: {suite_data["id"]})')
    #       db.session.rollback()
    #     return redirect(url_for('admin.suites'))
    #   elif 'name' in suite_data and 'version' in suite_data:
    #     suite = TestSuite.get_by_name_version(suite_data['name'], suite_data['version'])
    #     if suite:
    #       if suite.is_locked:
    #         flash('Unable to update Test Suite that is in use or marked final.')
    #         return redirect(url_for('admin.suites'))
    #       # Try to update existing suite
    #       try:
    #         suite.import_update(suite_data)
    #         db.session.commit()
    #         return redirect(url_for('admin.suite', suiteid=suite.id))
    #       except:
    #         flash('Invalid Data')
    #         db.session.rollback()
    #     else:
    #       # Create new suite
    #       try:
    #         suite = TestSuite(name=suite_data['name'], version=suite_data['version'])
    #         db.session.add(suite)
    #         db.session.commit()
    #         suite.import_update(suite_data)
    #         db.session.commit()
    #       except:
    #         db.session.rollback()
    #       return redirect(url_for('admin.suite', suiteid=suite.id))
    #   else:
    #     flash('Invalid Data')



  def _import_delete(self, meta_delete):
    del_targets = list()
    if 'case' in meta_delete:
      for suitecase in self.cases:
        if suitecase.case_id == meta_delete['case']:
          del_targets.append(suitecase)
    if 'sequence' in meta_delete:
      for suitecase in self.cases:
        if suitecase.sequence == meta_delete['sequence']:
          del_targets.append(suitecase)
    if 'suitecase' in meta_delete:
      for suitecase in self.cases:
        if suitecase.id == meta_delete['suitecase']:
          del_targets.append(suitecase)
    for target in del_targets:
      db.session.delete(target)

  def import_update(self, update_data):
    mode = ''
    if 'import_meta' in update_data:
      for meta in update_data['import_meta']:
        if 'mode' in meta:
          mode = meta['mode']
        elif 'delete' in meta:
          for meta_delete in meta['delete']:
            self._import_delete(meta_delete)
    if 'id' in update_data and update_data['id'] != self.id:
      flash(f'Invalid import data: "id": {update_data["id"]}')
      #raise ValidationError
      raise ValueError
    if 'name' in update_data:
      self.name = update_data['name']
    if 'version' in update_data:
      self.version = update_data['version']
    if 'archived' in update_data:
      self.archived = update_data['archived']
    if 'final' in update_data:
      self.final = update_data['final']
    if 'cases' in update_data:
      for update_suitecase in update_data['cases']:
        print('Update SuiteCase: ' + repr(update_suitecase))
        testcase = None
        if 'id' in update_suitecase['case']:
          testcase = TestCase.get_by_id(update_suitecase['case']['id'])
        if 'name' in update_suitecase['case'] and 'version' in update_suitecase['case']:
          testcase = TestCase.get_by_name_version(update_suitecase['case']['name'], update_suitecase['case']['version'])
        if testcase:
          print('Checkpoint')
          testcase.import_update(update_suitecase['case'])
          print('Checkpoint 2')
        else:
          try:
            testcase = TestCase(name=update_suitecase['case']['name'], version=update_suitecase['case']['version'])
            db.session.add(testcase)
            testcase.import_update(update_suitecase['case'])
          except:
            flash(f'Invalid import data: SuiteCase: {update_suitecase}')
        if 'id' in update_suitecase:
          suitecase = SuiteCase.get_by_id(update_suitecase['id'])
          if suitecase:
            suitecase.import_update(update_suitecase)
          else:
            suitecase = SuiteCase(id=update_suitecase['id'], sequence=update_suitecase['sequence'], suite_id=self.id, case_id=testcase.id)
            db.session.add(suitecase)
        elif 'sequence' in update_suitecase:
          suitecase = SuiteCase(sequence=update_suitecase['sequence'], suite_id=self.id, case_id=testcase.id)
          db.session.add(suitecase)


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

  def sequence_comments(self, sequence):
    seq = ''
    for c in str(sequence):
      if c.isdigit():
        seq = f'{seq}{c}'
      else:
        break
    seq = int(seq)
    #return Comment.query.where(Comment.sequence == seq).all()
    return [ comment for comment in self.comments if comment.sequence == seq ]
    
  def sequence_status(self, sequence):
    data = self.get_data()
    status = Results()
    comments = self.sequence_comments(sequence)
    for comment in comments:
      if comment.deleted:
        continue
      if comment.force_failure:
        #status['Manual Reject'] = False
        status.add(Result('Manual Reject', Result.Status.FAIL))
      elif comment.is_override:
        #status['Manual Override'] = True
        status.add(Result('Manual Override', Result.Status.PASS))
    if 'results' in data:
      data = { key:Results.fromJSON(val) for key, val in data['results'].items() }
      sequence = str(sequence)
      if sequence in data:
        #if isinstance(data[sequence], dict):
        #  status.update(data[sequence])
        status |= data[sequence]        
    return status

  def row_status(self, sequence):
    comments = self.sequence_comments(sequence)
    comment_status = ''
    for comment in comments:
      if comment.deleted:
        continue
      if comment.force_failure:
        comment_status = 'failure'
      elif comment.is_override:
        comment_status = 'success'
    if comment_status:
      return comment_status
    data = self.get_data()
    if 'results' not in data:
      return 'no data'
    results = data['results']
    if sequence in results:
      statuses = results[sequence]
    elif str(sequence) in results:
      statuses = results[str(sequence)]
    else:
      return 'no data'
    if not isinstance(statuses, dict):
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
  __table_args__ = (
    db.UniqueConstraint('name', 'version', name='_name_version_uc'),
  )

  suites: so.Mapped[List['SuiteCase']] = so.relationship('SuiteCase', primaryjoin='TestCase.id == SuiteCase.case_id')

  approver_role: so.Mapped[Role] = so.relationship(Role, primaryjoin='TestCase.approver_role_id == Role.id')

  def __repr__(self):
    return f'<TestCase({self.id}, {self.function}, {self.data})>'

  @classmethod
  def get_by_id(cls, id):
    return TestCase.query.where(TestCase.id == id).first()

  @classmethod
  def get_by_name_version(cls, name, version):
    res = TestCase.query.where(TestCase.name == name and TestCase.version == version).first()
    if res.name == name and res.version == version:
      return res
    return None

  def to_dict(self):
    return {
      'id': self.id,
      'name': self.name,
      'version': self.version,
      'description': self.description,
      'function': self.function,
      'data': self.data,
      'approver_role': self.approver_role.name,
      'archived': self.archived
    }

  @property
  def is_locked(self):
    return bool(self.suites)

  def import_update(self, update_data):
    if "meta" in update_data and update_data['meta'] == "match_only":
      return
    if "name" in update_data:
      self.name = update_data["name"]
    if "version" in update_data:
      self.version = update_data["version"]
    if "description" in update_data:
      self.description = update_data["description"]
    if "function" in update_data:
      self.function = update_data["function"]
    if "data" in update_data:
      self.data = json.dumps(json.loads(update_data["data"]), indent=4)
    if "approver_role_id" in update_data:
      self.approver_role_id = update_data["approver_role_id"]
    elif "approver_role" in update_data:
      try:
        self.approver_role = Role.query.where(Role.name == update_data["approver_role"])
      except:
        pass
    if "archived" in update_data:
      self.archived = update_data["archived"]

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

  @staticmethod
  def get_by_id(id):
    return SuiteCase.query.where(SuiteCase.id == id).first()


  

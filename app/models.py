from __future__ import annotations

import sqlalchemy as sa
import sqlalchemy.orm as so

import json
import secrets
import jwt
import redis
import rq

from datetime import datetime, timezone, timedelta
from hashlib import md5
from flask import current_app, url_for
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy.sql import false
from time import time
from typing import List, Optional

from app import db, login


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

  def __repr__(self):
    return f'<Device {self.devicename}>'


class TestSuite(db.Model):
  id: so.Mapped[int] = so.mapped_column(primary_key=True)
  name: so.Mapped[str] = so.mapped_column(sa.String(80), index=True)
  version: so.Mapped[str] = so.mapped_column(sa.String(12), nullable=True)
  archived: so.Mapped[bool] = so.mapped_column(sa.Boolean, server_default=sa.false())
  final: so.Mapped[bool] = so.mapped_column(sa.Boolean, server_default=sa.false())

  validations: so.WriteOnlyMapped['DeviceValidation'] = so.relationship(back_populates='suite')
  #cases: so.Mapped[List[Tuple['TestCase', str]]] = so.relationship(secondary=SuiteCase, back_populates='suites')
  cases: so.Mapped[List['SuiteCase']] = so.relationship('SuiteCase', primaryjoin='TestSuite.id == SuiteCase.suite_id')

  def __repr__(self):
    return f'<TesTSuite({self.id}, {self.name}, {self.version})>'

  def add_case(self, caseid, sequence):
    self.cases.append(SuiteCase(self.id, caseid, sequence))


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

  comments: so.WriteOnlyMapped['Comment'] = so.relationship(back_populates='device_validation')
  device: so.Mapped['Device'] = so.relationship(back_populates='validations')
  suite: so.Mapped['TestSuite'] = so.relationship(back_populates='validations')


class TestCase(db.Model):
  id: so.Mapped[int] = so.mapped_column(primary_key=True)
  name: so.Mapped[str] = so.mapped_column(sa.String(80), index=True)
  version: so.Mapped[str] = so.mapped_column(sa.String(12), nullable=True)
  function: so.Mapped[str] = so.mapped_column(sa.String(), nullable=True)
  data: so.Mapped[str] = so.mapped_column(sa.Text(), nullable=True)
  approver_role_id: so.Mapped[int] = so.mapped_column(sa.ForeignKey(Role.id), nullable=True)
  archived: so.Mapped[bool] = so.mapped_column(sa.Boolean, server_default=sa.false())

  suites: so.Mapped[List['SuiteCase']] = so.relationship('SuiteCase', primaryjoin='TestCase.id == SuiteCase.case_id')

  approver_role: so.Mapped[Role] = so.relationship(Role, primaryjoin='TestCase.approver_role_id == Role.id')

  def __repr__(self):
    return f'<TestCase({self.id}, {self.fucnction}, {self.data})>'

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


# SuiteCase = sa.Table(
#   'suite_case',
#   db.metadata,
#   sa.Column('suite_id', sa.Integer, sa.ForeignKey('test_suite.id'), primary_key=True),
#   sa.Column('case_id', sa.Integer, sa.ForeignKey('test_case.id'), primary_key=True),
#   sa.Column('sequence', sa.Integer, index=True),
# )


class SuiteCase(db.Model):
  suite_id: so.Mapped[int] = so.mapped_column(sa.ForeignKey(TestSuite.id), primary_key=True)
  case_id: so.Mapped[int] = so.mapped_column(sa.ForeignKey(TestCase.id), primary_key=True)
  sequence: so.Mapped[int] = so.mapped_column(sa.Integer, index=True)

  suite: so.Mapped[TestSuite] = so.relationship(TestSuite, primaryjoin='SuiteCase.suite_id == TestSuite.id', back_populates='cases')
  case: so.Mapped[TestCase] = so.relationship(TestCase, primaryjoin='SuiteCase.case_id == TestCase.id', back_populates='suites')

  def __init__(self, suite_id, case_id, sequence, *args, **kwargs):
    super().__init__(*args, **kwargs)
    self.suite_id = suite_id
    self.case_id = case_id
    self.sequence = sequence

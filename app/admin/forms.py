import sqlalchemy as sa

from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField, FieldList, FormField, FieldList, SelectField, TextAreaField
from wtforms import ValidationError
from wtforms_components import read_only
from wtforms.validators import ValidationError, DataRequired, Email, EqualTo, Length

from app import db
from app.models import User


class EditProfileForm(FlaskForm):
  username = StringField('Username', validators=[DataRequired()])
  display_name = StringField('Display Name', validators=[DataRequired()])
  about_me = StringField('About me')
  submit = SubmitField('Submit')

  def __init__(self, original_username, *args, **kwargs):
    super().__init__(*args, **kwargs)
    self.original_username = original_username

  def validate_username(self, username):
    if username.data != self.original_username:
      user = db.session.scalar(sa.select(User).where(
        User.username == username.data))
      if user is not None:
        raise ValidationError('Please use a different username.')


class RoleForm(FlaskForm):
  name = StringField('Role Name', validators=[DataRequired()])
  submit = SubmitField('Create Role')


class EditRoleForm(FlaskForm):
  name = StringField('Role Name', validators=[DataRequired()])
  active = BooleanField('Active')
  submit = SubmitField('Update Role')


#class TestSuite(db.Model):
#  id: so.Mapped[int] = so.mapped_column(primary_key=True)
#  name: so.Mapped[str] = so.mapped_column(sa.String(80), index=True)
#  version: so.Mapped[str] = so.mapped_column(sa.String(12), nullable=True)
#  archived: so.Mapped[bool] = so.mapped_column(default=False)

class NewTestSuiteForm(FlaskForm):
  name = StringField('Test Suite Name', validators=[Length(min=3, max=80)])
  version = StringField('Version', validators=[Length(min=0, max=12)])
  submit = SubmitField('Create Test Suite')


class TestSuiteForm(FlaskForm):
  name = StringField('Test Suite Name', validators=[Length(min=3, max=80)])
  version = StringField('Version', validators=[Length(min=0, max=12)])
  archived = BooleanField('Archived')
  submit = SubmitField('Update')


# SuiteCase = sa.Table(
#  'suite_case',
#  db.metadata,
#  sa.Column('suite_id', sa.Integer, sa.ForeignKey('test_suite.id'), primary_key=True),
#  sa.Column('case_id', sa.Integer, sa.ForeignKey('test_case.id'), primary_key=True),
#  sa.Column('sequence', sa.Integer, index=True),
#)

class AddSuiteCaseForm(FlaskForm):
  sequence = StringField('Sequence', validators=[Length(min=0, max=12)])
  case = SelectField('Test Case', validators=[DataRequired()])
  submit = SubmitField('Add Case')


class NewTestCaseForm(FlaskForm):
  name = StringField('Test Case Name', validators=[DataRequired()])
  version = StringField('Version', validators=[Length(min=0, max=12)])
  plugin = SelectField('Plugin', validators=[DataRequired()])
  description = TextAreaField('Description')
  data = TextAreaField('Plugin Data')
  approver_role = SelectField('Approver Role')
  submit = SubmitField('Add Case')

  def check_name(self, name):
    query = db.select(TestCase).where(TestCase.name == name and TestCase.version == self['version'])
    if db.session.scalars(query).all():
      raise ValidationError('Invalid name/version: in-use')


class TestCaseForm(FlaskForm):
  name = StringField('Name')
  version = StringField('Version')
  plugin = StringField('Plugin')
  description = TextAreaField('Description')
  data = TextAreaField('Plugin Data')
  approver_role = SelectField('Approver Role', validate_choice=False)
  submit = SubmitField('Update Case')

  def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)
    read_only(self.name)
    read_only(self.version)
    read_only(self.plugin)


class ImportForm(FlaskForm):
  textdata = TextAreaField('JSON Data', validators=[DataRequired()])
  submit = SubmitField('Import')


class ExportForm(FlaskForm):
  textdata = TextAreaField('JSON Data', validators=[DataRequired()])

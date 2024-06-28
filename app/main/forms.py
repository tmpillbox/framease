import sqlalchemy as sa

from flask import request
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, TextAreaField, IntegerField, SelectField, validators
from wtforms_components import read_only
from wtforms.validators import ValidationError, DataRequired, Length


class EmptyForm(FlaskForm):
  submit = SubmitField('Submit')


class EditProfileForm(FlaskForm):
  username = StringField('Username')
  display_name = StringField('Display Name', [validators.DataRequired()])
  about_me = StringField('About me')
  submit = SubmitField('Submit')

  def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)
    read_only(self.username)


class DeviceForm(FlaskForm):
  devicename = StringField('Device Name', validators=[DataRequired()])
  ip_or_hostname = StringField('IP or Hostname', validators=[DataRequired()])
  ssh_port = IntegerField('SSH Port', validators=[DataRequired()])
  https_port = IntegerField('Admin HTTPS Port', validators=[DataRequired()])
  submit = SubmitField('Create Device')


class TestSuiteForm(FlaskForm):
  suitename = StringField('Test Suite Name', validators=[DataRequired()])


class TestCaseForm(FlaskForm):
  sequence_number = IntegerField('Sequence', validators=[DataRequired()])
  test_function = SelectField('Test Function', validators=[DataRequired()])


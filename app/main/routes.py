import sqlalchemy as sa

from datetime import datetime, timezone
from flask import render_template, flash, redirect, url_for, request, g, current_app
from flask_login import current_user, login_required
from sqlalchemy.sql.expression import false

from app import db, plugins, validation_models
from app.main.forms import DeviceForm, EmptyForm, TestCaseForm, TestSuiteForm, EditProfileForm, NewDeviceValidationModelForm
from app.models import User, Device, TestSuite, TestCase, DeviceValidation, Notification, DeviceValidationModel
from app.main import bp


@bp.route('/', methods=['GET', 'POST'])
@bp.route('/index', methods=['GET', 'POST'])
@login_required
def index():
  page = request.args.get('page', 1, type=int)
  query = sa.select(Device).order_by(Device.devicename.desc())
  devices = db.paginate(query, page=page,
    per_page=current_user.page_size, error_out=False)
  next_url = url_for('main.index', page=devices.next_num) \
    if devices.has_next else None
  prev_url = url_for('main.index', page=devices.prev_num) \
    if devices.has_prev else None
  return render_template('index.html', title='Framease',
    devices=devices, next_url=next_url, prev_url=prev_url)


@bp.route('/user/<username>')
@login_required
def user(username):
  user = db.first_or_404(sa.select(User).where(User.username == username))
  return render_template('user.html', user=user)


@bp.route('/edit_profile', methods=['GET', 'POST'])
@login_required
def edit_profile():
  form = EditProfileForm()
  if request.method == 'POST' and form.validate():
    current_user.display_name = form.display_name.data
    current_user.about_me = form.about_me.data
    db.session.commit()
    flash('Your changes have been saved.')
    return redirect(url_for('main.edit_profile'))
  elif request.method == 'POST':
    form.username.data = current_user.username
    form.display_name.data = current_user.display_name
    form.about_me.data = current_user.about_me    
  elif request.method == 'GET':
    form.username.data = current_user.username
    form.display_name.data = current_user.display_name
    form.about_me.data = current_user.about_me
  return render_template('edit_profile.html', title='Edit Profile', form=form)


@bp.route('/notifications')
@login_required
def notifications():
  since = request.args.get('since', 0.0, type=float)
  query = current_user.notifications.select().where(
    Notification.timestamp > since).order_by(Notification.timestamp.asc())
  notifications = db.session.scalars(query)
  return [{
    'name': n.name,
    'data': n.get_data(),
    'timestamp': n.timestamp
  } for n in notifications ]


@bp.route('/device/new', methods=['GET', 'POST'])
def new_device():
  form = DeviceForm()
  if form.validate_on_submit():
    device = Device(devicename=form.devicename.data, hostname=form.ip_or_hostname.data,
      ssh_port=form.ssh_port.data, https_port=form.https_port.data)
    db.session.add(device)
    db.session.commit()
    flash("Device created.")
    return redirect(url_for('main.device', deviceid=device.id))
  else:
    form.ssh_port.data = 222
    form.https_port.data = 4443
    return render_template('new_device.html', form=form)


@bp.route('/device/<int:deviceid>', methods=['GET', 'POST'])
@login_required
def device(deviceid):
  device = db.first_or_404(sa.select(Device).where(Device.id == deviceid))
  query = device.validations.select().order_by(DeviceValidation.timestamp.desc())
  validations = db.session.scalars(query).all()
  form = EmptyForm()
  return render_template('device.html', device=device, validations=validations)


# class DeviceValidationModel(db.Model):
#   id: so.Mapped[int] = so.mapped_column(primary_key=True)
#   device_id: so.Mapped[int] = so.mapped_column(ForeignKey(Device.id), index=True)
#   validation_model: so.Mapped[str] = so.mapped_column(sa.String())
#   validation_model_data: so.Mapped[str] = so.mapped_column(sa.Text(), nullable=True)

@bp.route('/device/<int:deviceid>/validation_models', methods=['GET', 'POST'])
@login_required
def edit_device_models(deviceid):
  # page = request.args.get('page', 1, type=int)
  # form = NewTestCaseForm()
  # form.plugin.choices = [ plugin_name for plugin_name in plugins ]
  # query = sa.select(Role).where(Role.active == True).order_by(Role.name.asc())
  # all_roles = db.session.scalars(query).all()
  # form.approver_role.choices = [ (role.id, role.name) for role in all_roles ]
  # if form.validate_on_submit():
  #   case = TestCase(name=form.name.data, version=form.version.data,
  #     function=form.plugin.data, data=form.data.data,
  #     approver_role_id=form.approver_role.data, archived=False)
  #   db.session.add(case)
  #   db.session.commit()
  #   return redirect(url_for('admin.cases', page=page))
  # elif request.method == 'POST':
  #   flash(f'Error: {form.errors}')
  device = db.first_or_404(sa.select(Device).where(Device.id == deviceid))
  form = NewDeviceValidationModelForm()
  form.model.choices = [ model_name for model_name in validation_models ]
  if form.validate_on_submit():
    model = DeviceValidationModel(device_id=device.id, 
      validation_model=form.model.data
    )
    db.session.add(model)
    db.session.commit()
    return redirect(url_for('main.edit_device_models', deviceid=deviceid))
  # query = sa.select(TestCase).order_by(TestCase.name.desc())
  # cases = db.paginate(query, page=page,
  #   per_page=current_user.page_size,
  #   error_out=False)
  # next_url = url_for('admin.cases', page=cases.next_num) \
  #   if cases.has_next else None
  # prev_url = url_for('admin.cases', page=cases.prev_num) \
  #   if cases.has_prev else None
  # return render_template('admin/cases.html', title='Test Case Administration',
  #   cases=cases, next_url=next_url, prev_url=prev_url, form=form)
  empty_form = EmptyForm()
  return render_template('device_models.html', title=f'Device Validation Models',
    device=device, form=form, empty_form=empty_form)


@bp.route('/device/<int:deviceid>/validation_models/<modelid>/delete', methods=['POST'])
@login_required
def device_delete_model(deviceid, modelid):
  DeviceValidationModel.query.filter(DeviceValidationModel.id == modelid, DeviceValidationModel.device_id == deviceid).delete()
  db.session.commit()
  return redirect(url_for('main.edit_device_models', deviceid=deviceid))

@bp.route('/device/<int:deviceid>/validation_models/<modelid>/configure')
@login_required
def device_configure_model(deviceid, modelid):
  model = db.first_or_404(sa.select(
    DeviceValidationModel).where(
      DeviceValidationModel.id == modelid
    ).where(
      DeviceValidationModel.device_id == deviceid
    )
  )
  return render_template('config_model.html', title=f'Configure Device Validation Model',
    model=model
  )

import sqlalchemy as sa

from datetime import datetime, timezone
from flask import render_template, flash, redirect, url_for, request, g, current_app
from flask_login import current_user, login_required
from sqlalchemy.sql.expression import false

from app import db, plugins
from app.main.forms import DeviceForm, EmptyForm, TestCaseForm, TestSuiteForm, EditProfileForm
from app.models import User, Device, TestSuite, TestCase, DeviceValidation, Notification
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


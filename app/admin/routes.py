import sqlalchemy as sa

from flask import render_template, redirect, url_for, flash, request, current_app
from flask_login import current_user, login_required, login_user, logout_user
from functools import wraps
from urllib.parse import urlsplit

from app import db, plugins
from app.admin import bp
from app.admin.forms import EditProfileForm, NewTestSuiteForm, TestSuiteForm, AddSuiteCaseForm, RoleForm, EditRoleForm, NewTestCaseForm, TestCaseForm
from app.main.forms import EmptyForm
from app.models import User, Role, TestSuite, TestCase, DeviceValidation, Device
from app.auth.email import send_password_reset_email

EXEMPT_METHODS = []

def admin_required(func):
  @wraps(func)
  def decorated_view(*args, **kwargs):
    if request.method in EXEMPT_METHODS:
      return func(*args, **kwargs)
    elif not current_user.admin:
      abort(403)
    return func(*args, **kwargs)
  return decorated_view


@bp.route('/')
@bp.route('/index')
@login_required
@admin_required
def index():
  return render_template('admin/index.html', title='Admin Portal')


@bp.route('/users')
@login_required
@admin_required
def users():
  page = request.args.get('page', 1, type=int)
  form = EmptyForm()
  query = sa.select(User).order_by(User.display_name.desc())
  users = db.paginate(query, page=page,
    per_page=current_user.page_size,
    error_out=False)
  next_url = url_for('admin.users', page=users.next_num) \
    if users.has_next else None
  prev_url = url_for('admin.users', page=users.prev_num) \
    if users.has_prev else None
  return render_template('admin/users.html', title='User Administration',
    users=users, next_url=next_url, prev_url=prev_url, form=form)


@bp.route('/roles', methods=['GET', 'POST'])
@login_required
@admin_required
def roles():
  page = request.args.get('page', 1, type=int)
  form = RoleForm()
  if form.validate_on_submit():
    role = Role(name=form.name.data)
    db.session.add(role)
    db.session.commit()
    return redirect(url_for('admin.roles', page=page))
  else:
    query = sa.select(Role).order_by(Role.name.asc())
    roles = db.paginate(query, page=page,
      per_page=current_user.page_size,
      error_out=False)
    next_url = url_for('admin.roles', page=roles.next_num) \
      if roles.has_next else None
    prev_url = url_for('admin.roles', page=roles.prev_num) \
      if roles.has_prev else None
    return render_template('admin/roles.html', title='Roles Administration',
      roles=roles, next_url=next_url, prev_url=prev_url, form=form)

@bp.route('/edit_role/<roleid>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_role(roleid):
  role = db.first_or_404(sa.select(Role).where(Role.id == roleid))
  form = EditRoleForm()
  if form.validate_on_submit():
    role.name = form.name.data
    role.active = form.active.data
    db.session.commit()
    flash('Your changes have been saved.')
    return redirect(url_for('admin.edit_role', roleid=roleid))
  elif request.method == 'GET':
    form.name.data = role.name
    form.active.data = role.active
  return render_template('admin/edit_role.html', title='Admin: Edit Role', form=form)


@bp.route('/activate_role/<roleid>', methods=['POST'])
@login_required
@admin_required
def activate_role(roleid):
  role = db.first_or_404(sa.select(Role).where(Role.id == roleid))
  form = EmptyForm()
  if form.validate_on_submit():
    role.active = True
    db.session.commit()
    flash('Role Activated')
  return redirect(url_for('admin.roles', page=request.args.get('page', 1, type=int)))


@bp.route('/deactivate_role/<roleid>', methods=['POST'])
@login_required
@admin_required
def deactivate_role(roleid):
  role = db.first_or_404(sa.select(Role).where(Role.id == roleid))
  form = EmptyForm()
  if form.validate_on_submit():
    role.active = False
    db.session.commit()
    flash('Role Deactivated')
  return redirect(url_for('admin.roles', page=request.args.get('page', 1, type=int)))


@bp.route('/suites', methods=['GET', 'POST'])
@login_required
@admin_required
def suites():
  page = request.args.get('page', 1, type=int)
  form = NewTestSuiteForm()
  if form.validate_on_submit():
    suite = TestSuite(name=form.name.data, version=form.version.data)
    db.session.add(suite)
    db.session.commit()
    return redirect(url_for('admin.suites', page=page))
  query = sa.select(TestSuite).order_by(TestSuite.name.desc())
  suites = db.paginate(query, page=page,
    per_page=current_user.page_size,
    error_out=False)
  next_url = url_for('admin.suites', page=suites.next_num) \
    if suites.has_next else None
  prev_url = url_for('admin.suites', page=suites.prev_num) \
    if suites.has_prev else None
  return render_template('admin/suites.html', title='Roles Administration',
    suites=suites, next_url=next_url, prev_url=prev_url, form=form)

#class TestSuite(db.Model):
#  id: so.Mapped[int] = so.mapped_column(primary_key=True)
#  name: so.Mapped[str] = so.mapped_column(sa.String(80), index=True)
#  version: so.Mapped[str] = so.mapped_column(sa.String(12), nullable=True)
#  archived: so.Mapped[bool] = so.mapped_column(default=False)


@bp.route('/suite/<suiteid>/archive', methods=['POST'])
@login_required
@admin_required
def archive_suite(suiteid):
  suite = db.first_or_404(sa.select(TestSuite).where(TestSuite.id == suiteid))
  form = EmptyForm()
  if form.validate_on_submit():
    suite.archived = True
    db.session.commit()
    flash('Test Suite Archived.')
  return redirect(url_for('admin.suites', page=request.args.get('page', 1, type=int)))


@bp.route('/suite/<suiteid>/unarchive', methods=['POST'])
@login_required
@admin_required
def unarchive_suite(suiteid):
  suite = db.first_or_404(sa.select(TestSuite).where(TestSuite.id == suiteid))
  form = EmptyForm()
  if form.validate_on_submit():
    suite.archived = False
    db.session.commit()
    flash('Test Suite Unarchived.')
  return redirect(url_for('admin.suites', page=request.args.get('page', 1, type=int)))


@bp.route('/suite/<suiteid>/lock', methods=['POST'])
@login_required
@admin_required
def lock_suite(suiteid):
  suite = db.first_or_404(sa.select(TestSuite).where(TestSuite.id == suiteid))
  if suite.archived:
    flash('Test Suite is Archived. Unarchive before making any changes.', 'warning')
    return redirect(url_for('admin.suites', page=request.args.get('page', 1, type=int)))
  form = EmptyForm()
  if form.validate_on_submit():
    suite.final = True
    db.session.commit()
    flash('Test Suite Locked.')
  return redirect(url_for('admin.suites', page=request.args.get('page', 1, type=int)))


@bp.route('/suite/<suiteid>/unlock', methods=['POST'])
@login_required
@admin_required
def unlock_suite(suiteid):
  suite = db.first_or_404(sa.select(TestSuite).where(TestSuite.id == suiteid))
  if suite.archived:
    flash('Test Suite is Archived. Unarchive before making any changes.', 'warning')
    return redirect(url_for('admin.suites', page=request.args.get('page', 1, type=int)))  
  form = EmptyForm()
  if form.validate_on_submit():
    suite.final = False
    db.session.commit()
    flash('Test Suite Unlocked.')
  return redirect(url_for('admin.suites', page=request.args.get('page', 1, type=int)))


@bp.route('/suite/new', methods=['GET', 'POST'])
@login_required
@admin_required
def new_suite():
  form = NewTestSuiteForm()
  if form.validate_on_submit():
    suite = TestSuite(name=form.name.data, version=form.version.data)
    db.session.add(suite)
    db.session.commit()
    return redirect(url_for('admin.suite', suiteid=suite.id))
  else:
    return render_template('admin/new_test_suite.html', title='Create Test Suite', form=form)


@bp.route('/suite/<suiteid>', methods=['GET', 'POST'])
@login_required
@admin_required
def suite(suiteid):
  suite = db.first_or_404(sa.select(TestSuite).where(TestSuite.id == suiteid))
  form = TestSuiteForm()
  if form.validate_on_submit():
    suite.name = form.name.data
    suite.version = form.version.data
    suite.archived = form.archived.data
    db.session.commit()
    return redirect(url_for('admin.suites', page=request.args.get('page', 1, type=int)))
  else:
    form.name.data = suite.name
    form.version.data = suite.version
    form.archived.data = suite.archived
  return render_template(f'admin/test_suite.html', title='Test Suite: {suite.name} ({suite.version})', suite=suite, form=form)


@bp.route('/suite/<suiteid>/cases', methods=['GET', 'POST'])
@login_required
@admin_required
def suite_cases(suiteid):
  suite = db.first_or_404(sa.select(TestSuite).where(TestSuite.id == suiteid))
  form = AddSuiteCaseForm()
  if form.validate_on_submit():
    suite.add_case(form.case.data, form.sequence.data)
    flash('Case added.')
    return redirect(url_for('admin.suite_cases', suite=suite, page=request.args.get('page', 1, type=int)))
  query = sa.select(TestCase).where(TestCase.archived == False).order_by(TestCase.name.asc(), TestCase.version.asc())
  all_cases = db.session.scalars(query).all()
  cases = suite.cases
  form.case.choices = [ (c.id, c.name) for c in all_cases if c not in cases ]
  return render_template('admin/suite_cases.html', suite=suite, cases=cases, form=form)


@bp.route('/suite/<suiteid>/add_case', methods=['POST'])
@login_required
@admin_required
def add_suite_case(suiteid):
  suite = db.first_or_404(sa.select(TestSuite).where(TestSuite.id == suiteid))
  if suite.archived:
    flash('Test Suite is Archived.', 'error')
  elif suite.final:
    flash('Test Suite is Locked.', 'error')
  form = AddSuiteCaseForm()
  if form.validate_on_submit():
    suite.add_case(form.case.data, form.sequence.data)
    db.session.commit()
    flash('Case added.')
  else:
    flash('An error occured. Case not added.')
  return redirect(url_for('admin.suite_cases', suiteid=suiteid))


@bp.route('/suite/<suiteid>/delete_case/<suitecaseid>', methods=['POST'])
@login_required
@admin_required
def delete_suite_case(suiteid, suitecaseid):
  form = EmptyForm()
  if form.validate_on_submit():
    suite = db.first_or_404(sa.select(TestSuite).where(TestSuite.id == suiteid))
    suite.del_case(suitecaseid)
    db.session.commit()
    flash('Case deleted.')
  else:
    flash('An error occured. Case not deleted.')
  return redirect(url_for('admin.suite_cases', suiteid=suiteid))


@bp.route('/cases', methods=['GET', 'POST'])
@login_required
@admin_required
def cases():
  page = request.args.get('page', 1, type=int)
  form = NewTestCaseForm()
  form.plugin.choices = [ plugin_name for plugin_name in plugins ]
  query = sa.select(Role).where(Role.active == True).order_by(Role.name.asc())
  all_roles = db.session.scalars(query).all()
  form.approver_role.choices = [ (role.id, role.name) for role in all_roles ]
  if form.validate_on_submit():
    case = TestCase(name=form.name.data, version=form.version.data,
      function=form.plugin.data, data=form.data.data,
      approver_role_id=form.approver_role.data, archived=False)
    db.session.add(case)
    db.session.commit()
    return redirect(url_for('admin.cases', page=page))
  elif request.method == 'POST':
    flash(f'Error: {form.errors}')

  query = sa.select(TestCase).order_by(TestCase.name.desc())
  cases = db.paginate(query, page=page,
    per_page=current_user.page_size,
    error_out=False)
  next_url = url_for('admin.cases', page=cases.next_num) \
    if cases.has_next else None
  prev_url = url_for('admin.cases', page=cases.prev_num) \
    if cases.has_prev else None
  return render_template('admin/cases.html', title='Test Case Administration',
    cases=cases, next_url=next_url, prev_url=prev_url, form=form)


@bp.route('/case/<caseid>', methods=['GET', 'POST'])
@login_required
@admin_required
def case(caseid):
  case = db.first_or_404(sa.select(TestCase).where(TestCase.id == caseid))
  query = sa.select(Role).where(Role.active == True).order_by(Role.name.asc())
  all_roles = db.session.scalars(query).all()
  form = TestCaseForm()
  form.approver_role.choices = [ (role.id, role.name) for role in all_roles ]
  if form.validate_on_submit():
    case.data = form.data.data
    case.approver_role_id = form.approver_role.data
    db.session.commit()
    return redirect(url_for('admin.cases', page=request.args.get('page', 1, type=int)))
  elif request.method == 'POST':
    flash(form.errors)
  form.approver_role.default = case.approver_role.id
  form.process()
  form.name.data = case.name
  form.version.data = case.version
  form.plugin.data = case.function
  form.data.data = case.data
  return render_template('admin/test_case.html', title=f'Test Case: {case.name} ({case.version})',
    case=case, form=form)


@bp.route('/case/<caseid>/archive', methods=['POST'])
@login_required
@admin_required
def archive_case(caseid):
  case = db.first_or_404(sa.select(TestCase).where(TestCase.id == caseid))
  suites_using = [
    ( suite.id, f'{suite.name} ({suite.version})' )
    for suite in case.suites
    if suite.archived is False
  ]
  if suites_using:
    flash('Test Case is in use. Please archive or unlink:')
    for suiteid, suite_name in suites_using:
      flash('<a href="' + url_for('admin.suite', suiteid=suiteid) + ">" + suite_name + "</a>")
    return redirect(url_for('admin.cases', page=request.args.get('page', 1, type=int)))
  form = EmptyForm()
  if form.validate_on_submit():
    case.archived = True
    db.session.commit()
    flash('Test Case Archived.')
  return redirect(url_for('admin.cases', page=request.args.get('page', 1, type=int)))


@bp.route('/case/<caseid>/unarchive', methods=['POST'])
@login_required
@admin_required
def unarchive_case(caseid):
  case = db.first_or_404(sa.select(TestCase).where(TestCase.id == caseid))
  form = EmptyForm()
  if form.validate_on_submit():
    case.archived = False
    db.session.commit()
    flash('Test Case Unarchived.')
  return redirect(url_for('admin.cases', page=request.args.get('page', 1, type=int)))



@bp.route('/edit_user/<username>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_user(username):
  user = db.first_or_404(sa.select(User).where(User.username == username))
  form = EditProfileForm(user.username)
  if form.validate_on_submit():
    user.username = form.username.data
    user.display_name = form.display_name.data
    user.about_me = form.about_me.data
    db.session.commit()
    flash('Your changes have been saved.')
    return redirect(url_for('admin.users'))
  elif request.method == 'GET':
    form.username.data = user.username
    form.display_name.data = user.display_name
    form.about_me.data = user.about_me
  return render_template('admin/edit_user.html', title='Admin: Edit User Profile', form=form)


@bp.route('/edit_user/<username>/make_admin', methods=['POST'])
@login_required
@admin_required
def make_admin(username):
  form = EmptyForm()
  if form.validate_on_submit():
    user = db.first_or_404(sa.select(User).where(User.username == username))
    user.admin = True
    db.session.commit()
    flash(f'User {user.display_name} (@{user.username}) is now an Administrator')
  return redirect(url_for('admin.users', page=request.args.get('page', 1, type=int)))


@bp.route('/edit_user/<username>/remove_admin', methods=['POST'])
@login_required
@admin_required
def remove_admin(username):
  form = EmptyForm()
  if form.validate_on_submit():
    user = db.first_or_404(sa.select(User).where(User.username == username))
    user.admin = False
    db.session.commit()
    flash(f'User {user.display_name} (@{user.username}) is no longer an Administrator')
  return redirect(url_for('admin.users', page=request.args.get('page', 1, type=int)))


@bp.route('/edit_user/<username>/roles', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_user_roles(username):
  user = db.first_or_404(sa.select(User).where(User.username == username))
  query = sa.select(Role).where(Role.active == True).order_by(Role.name.asc())
  form = EmptyForm()
  all_roles = db.session.scalars(query).all()
  roles = user.roles
  return render_template('admin/user_roles.html', user=user, roles=roles, all_roles=all_roles, form=form)


@bp.route('/edit_user/<username>/activate_role/<roleid>', methods=['POST'])
@login_required
@admin_required
def activate_user_role(username, roleid):
  form = EmptyForm()
  if form.validate_on_submit():
    user = db.first_or_404(sa.select(User).where(User.username == username))
    role = db.first_or_404(sa.select(Role).where(Role.id == roleid))
    user.add_role(role)
    db.session.commit()
    flash('Role Activated')
  return redirect(url_for('admin.edit_user_roles', username=username, page=request.args.get('page', 1, type=int)))


@bp.route('/edit_user/<username>/deactivate_role/<roleid>', methods=['POST'])
@login_required
@admin_required
def deactivate_user_role(username, roleid):
  form = EmptyForm()
  if form.validate_on_submit():
    user = db.first_or_404(sa.select(User).where(User.username == username))
    role = db.first_or_404(sa.select(Role).where(Role.id == roleid))
    user.remove_role(role)
    db.session.commit()
    flash('Role Deactivated')
  return redirect(url_for('admin.edit_user_roles', username=username, page=request.args.get('page', 1, type=int)))

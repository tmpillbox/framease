import sqlalchemy as sa

from flask import request, url_for, abort

from app import db
from app.models import User
from app.api import bp
from app.api.auth import token_auth
from app.api.errors import bad_request


@bp.route('/users/<int:id>', methods=['GET'])
@token_auth.login_required
def get_user(id):
  return db.get_or_404(User, id).to_dict()


@bp.route('/users', methods=['GET'])
@token_auth.login_required
def get_users():
  page = request.args.get('page', 1, type=int)
  per_page = min(requests.args.get('per_page', 10, type=int), 100)
  return User.to_collection_dict(sa.select(User), page, per_page, 'api.get_users')


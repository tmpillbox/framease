import click
import os

from flask import Blueprint

bp = Blueprint('cli', __name__, cli_group=None)

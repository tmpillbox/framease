"""validation model sequence

Revision ID: 21b5446056f2
Revises: b4d0e93bf9bb
Create Date: 2024-07-01 10:44:30.041849

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '21b5446056f2'
down_revision = 'b4d0e93bf9bb'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('device_validation_model', schema=None) as batch_op:
        batch_op.add_column(sa.Column('sequence', sa.Integer(), nullable=False))
        batch_op.create_index(batch_op.f('ix_device_validation_model_sequence'), ['sequence'], unique=False)

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('device_validation_model', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_device_validation_model_sequence'))
        batch_op.drop_column('sequence')

    # ### end Alembic commands ###

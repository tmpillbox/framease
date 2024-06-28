"""device validation models

Revision ID: b4d0e93bf9bb
Revises: 5f9b5e7304d7
Create Date: 2024-06-28 11:59:36.656399

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b4d0e93bf9bb'
down_revision = '5f9b5e7304d7'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('device_validation_model',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('device_id', sa.Integer(), nullable=False),
    sa.Column('validation_model', sa.String(), nullable=False),
    sa.Column('validation_model_data', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['device_id'], ['device.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('device_validation_model', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_device_validation_model_device_id'), ['device_id'], unique=False)

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('device_validation_model', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_device_validation_model_device_id'))

    op.drop_table('device_validation_model')
    # ### end Alembic commands ###
"""add account_focus to source

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-04-22 10:00:00.000000

"""

from alembic import op

revision = "b2c3d4e5f6a7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE source ADD COLUMN IF NOT EXISTS account_focus VARCHAR")


def downgrade():
    op.execute("ALTER TABLE source DROP COLUMN IF EXISTS account_focus")

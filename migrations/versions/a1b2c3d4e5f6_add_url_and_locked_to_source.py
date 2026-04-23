"""add url and locked to source

Adds url (varchar) and locked (boolean) columns to the source table
to support storing account metadata such as profile URLs and account status.

Revision ID: a1b2c3d4e5f6
Revises: cdaa80fb493a
Create Date: 2026-04-22 09:00:00.000000

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "a1b2c3d4e5f6"
down_revision = "cdaa80fb493a"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE source ADD COLUMN IF NOT EXISTS url VARCHAR")
    op.execute("ALTER TABLE source ADD COLUMN IF NOT EXISTS locked BOOLEAN DEFAULT FALSE")


def downgrade():
    op.execute("ALTER TABLE source DROP COLUMN IF EXISTS url")
    op.execute("ALTER TABLE source DROP COLUMN IF EXISTS locked")

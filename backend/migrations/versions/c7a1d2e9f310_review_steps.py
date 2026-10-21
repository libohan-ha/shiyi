"""Store the per-step breakdown behind each review's 贯通率."""

import sqlalchemy as sa
from alembic import op

revision = "c7a1d2e9f310"
down_revision = "b521cf13a902"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("reviews", sa.Column("steps", sa.JSON(), nullable=False, server_default="[]"))


def downgrade():
    op.drop_column("reviews", "steps")

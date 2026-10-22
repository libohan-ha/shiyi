"""Store the 贯通率 steps recorded when an entry is added."""

import sqlalchemy as sa
from alembic import op

revision = "d4b8e6f1a205"
down_revision = "c7a1d2e9f310"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("items", sa.Column("initial_steps", sa.JSON(), nullable=False, server_default="[]"))


def downgrade():
    op.drop_column("items", "initial_steps")

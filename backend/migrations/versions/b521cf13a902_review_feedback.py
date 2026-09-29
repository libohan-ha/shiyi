"""Store problem feedback and source links for focused review tasks."""

import sqlalchemy as sa
from alembic import op

revision = "b521cf13a902"
down_revision = "9ce1295fcf53"
branch_labels = None
depends_on = None


def upgrade():
    if op.get_bind().dialect.name == "sqlite":
        # Rebuilding items with foreign keys enabled cascades into cards and history.
        # A nullable inline reference can be added without replacing the table.
        op.execute("ALTER TABLE items ADD COLUMN source_item_id VARCHAR(36) "
                   "CONSTRAINT fk_items_source_item_id REFERENCES items (id) ON DELETE SET NULL")
    else:
        op.add_column("items", sa.Column("source_item_id", sa.String(36), nullable=True))
        op.create_foreign_key("fk_items_source_item_id", "items", "items", ["source_item_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_items_source_item_id", "items", ["source_item_id"])
    op.add_column("reviews", sa.Column("independent_completed", sa.Boolean(), nullable=True))
    op.add_column("reviews", sa.Column("blocker", sa.Text(), nullable=False, server_default=""))


def downgrade():
    op.drop_column("reviews", "blocker")
    op.drop_column("reviews", "independent_completed")
    op.drop_index("ix_items_source_item_id", table_name="items")
    if op.get_bind().dialect.name != "sqlite":
        op.drop_constraint("fk_items_source_item_id", "items", type_="foreignkey")
    # SQLite's native DROP COLUMN removes the inline reference, without rebuilding items.
    op.drop_column("items", "source_item_id")

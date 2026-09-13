from alembic import context

from app import models  # noqa: F401 -- register all tables in Alembic's target metadata
from app.config import settings
from app.database import Base, engine

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))

if context.is_offline_mode():
    context.configure(url=settings.database_url, target_metadata=Base.metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()

from alembic import context

from frameread.db.models import metadata

# 迁移只经 frameread.db.migrate 运行：调用方已持 advisory lock 并传入连接
connection = context.config.attributes["connection"]
context.configure(connection=connection, target_metadata=metadata, transactional_ddl=True)
with context.begin_transaction():
    context.run_migrations()

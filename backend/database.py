from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import event, text
from backend.config import DATABASE_URL

engine = create_async_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

def _sqlite_add_missing_columns(sync_conn) -> list:
    """create_all() creates missing TABLES but never adds new COLUMNS to existing ones, and
    Alembic is not wired up. A new model column therefore crashed every query on an existing
    database. For SQLite we add any missing nullable / defaulted column with ALTER TABLE.
    Idempotent. Columns that are NOT NULL without a default cannot be added this way and
    are reported instead of guessed."""
    from sqlalchemy import inspect
    added = []
    insp = inspect(sync_conn)
    existing_tables = set(insp.get_table_names())
    for table in Base.metadata.tables.values():
        if table.name not in existing_tables:
            continue
        have = {c["name"] for c in insp.get_columns(table.name)}
        for col in table.columns:
            if col.name in have:
                continue
            ddl_default = ""
            if not col.nullable:
                # SQLite refuses ADD COLUMN ... NOT NULL without a literal DEFAULT.
                scalar = getattr(col.default, "arg", None) if col.default is not None and col.default.is_scalar else None
                if scalar is None and col.server_default is None:
                    import logging
                    logging.getLogger("airdrop.db").error(
                        "Cannot auto-add NOT NULL column %s.%s without a scalar default; add it manually",
                        table.name, col.name)
                    continue
                if scalar is not None:
                    lit = int(scalar) if isinstance(scalar, bool) else scalar
                    lit = f"'{lit}'" if isinstance(lit, str) else str(lit)
                    ddl_default = f" NOT NULL DEFAULT {lit}"
                else:
                    ddl_default = f" NOT NULL DEFAULT {col.server_default.arg.text}"
            coltype = col.type.compile(dialect=sync_conn.dialect)
            sync_conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {coltype}{ddl_default}'))
            added.append(f"{table.name}.{col.name}")
    return added


async def init_db():
    # Enable WAL journal mode — required for safe concurrent multi-writer access
    # under the 4-slot worker pool model.
    async with engine.begin() as conn:
        await conn.execute(text("PRAGMA journal_mode=WAL"))
        await conn.execute(text("PRAGMA synchronous=NORMAL"))
        await conn.run_sync(Base.metadata.create_all)
        if conn.dialect.name == "sqlite":
            added = await conn.run_sync(_sqlite_add_missing_columns)
            if added:
                import logging
                logging.getLogger("airdrop.db").warning("Added missing columns: %s", ", ".join(added))

async def get_db():
    async with async_session() as session:
        yield session

from datetime import datetime, timezone

from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

from app.core.config import settings


def utcnow() -> datetime:
    """naive UTC（秒级截断）—— MySQL DATETIME(0) 四舍五入会把 .6s 进位成未来时间导致
    生效判断翻转，故统一 floor 到秒，保证写读对称"""
    return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)


_is_sqlite = settings.db_url.startswith("sqlite")

_engine_kwargs: dict = {"connect_args": {"check_same_thread": False}} if _is_sqlite else {
    # MySQL 默认 REPEATABLE READ：长事务快照读不到其它会话提交，读已提交更契合电商读多写少
    "isolation_level": "READ COMMITTED",
    "pool_pre_ping": True,
    "pool_recycle": 3600,
}
engine = create_engine(settings.db_url, **_engine_kwargs)


@event.listens_for(engine, "connect")
def _sqlite_pragma(dbapi_conn, _record):
    if _is_sqlite:
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA journal_mode=WAL")
        # 写锁竞争等待 10s：与 WAL 配合降低偶发 database is locked
        cur.execute("PRAGMA busy_timeout=10000")
        cur.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """MVP 用 create_all；接 MySQL 后切换 Flyway/Alembic 前向迁移"""
    from app import models  # noqa: F401

    Base.metadata.create_all(engine)

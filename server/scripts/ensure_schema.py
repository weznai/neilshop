"""存量库幂等 DDL 守卫 —— 供不跑 alembic 的部署（create_all 只建新表不改旧表）：
缺列则 ALTER ADD、列宽不足则 ALTER MODIFY，重复执行零副作用。
与 migrations/versions/b7f3a2c9d4e1 保持同一终态（exchanges.qty + payments 列宽 255）。
"""

import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import inspect, text  # noqa: E402

from app.core.db import engine  # noqa: E402

log = logging.getLogger("glowmag.schema")

# (表, 列, 期望 DDL/列宽) —— 新增加列迁移在此登记即可扩展
_INT_COLUMNS = [
    # (table, column, DDL)
    ("exchanges", "qty", "ALTER TABLE exchanges ADD COLUMN qty INT NOT NULL DEFAULT 1"),
]
_VARCHAR_COLUMNS = [
    # (table, column, 期望宽度, MODIFY DDL) —— MySQL 专用（sqlite 动态类型无需扩宽）
    ("payments", "stripe_checkout_session", 255,
     "ALTER TABLE payments MODIFY stripe_checkout_session VARCHAR(255)"),
]


def ensure_schema() -> None:
    """幂等补齐存量库缺列/窄列（information_schema / inspect 双方言探测）。"""
    with engine.begin() as conn:
        insp = inspect(conn)
        for table, column, ddl in _INT_COLUMNS:
            names = [c["name"] for c in insp.get_columns(table)]
            if names and column not in names:
                conn.execute(text(ddl))
                log.warning("ensure_schema: added %s.%s via DDL guard", table, column)
        if engine.dialect.name == "mysql":
            for table, column, width, ddl in _VARCHAR_COLUMNS:
                row = conn.execute(text(
                    "SELECT CHARACTER_MAXIMUM_LENGTH FROM information_schema.COLUMNS "
                    "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t AND COLUMN_NAME = :c"
                ), {"t": table, "c": column}).first()
                if row and row[0] is not None and int(row[0]) < width:
                    conn.execute(text(ddl))
                    log.warning("ensure_schema: widened %s.%s to %d chars", table, column, width)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    ensure_schema()
    print("ensure_schema done")

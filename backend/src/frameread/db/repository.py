from typing import Any

from sqlalchemy import ColumnElement, Table, Update, update

# Repository 只构造语句、不执行不 commit（Q3、R4）；执行与影响行数检查在 UoW


def versioned_update(table: Table, where: ColumnElement[bool], expected_version: int, **values: Any) -> Update:
    """乐观锁条件更新：WHERE version = :expected，并显式 version + 1（Q9）。"""
    if "version" in values:
        raise ValueError("version 由 versioned_update 递增，调用方不得设置")
    return update(table).where(where, table.c.version == expected_version).values(**values, version=table.c.version + 1)

"""ORM 基类与命名约定。

为什么定义 naming_convention：
- SQLAlchemy 默认给约束/索引生成"匿名"或随机名，Alembic 在 `--autogenerate`
  对比模型与数据库差异时，无法稳定地识别"这个约束改了名"，容易产生无意义的迁移。
- 显式命名约定让每个约束/索引都有可预测的名字，迁移脚本干净、可重复、可回滚。
"""

from __future__ import annotations

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# 约束/索引命名约定（Alembic 官方推荐）
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """所有 ORM 模型的基类。metadata 绑定命名约定，供 Alembic 比对。"""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)

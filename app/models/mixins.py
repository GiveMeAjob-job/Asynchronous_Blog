# app/models/mixins.py (或您定义 TimestampMixin 的地方)
from sqlalchemy import Column, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column # <--- 导入 Mapped 和 mapped_column
from datetime import datetime

class TimestampMixin:
    # 使用 Mapped[] 来注解列，并使用 mapped_column() 代替 Column()
    # mapped_column() 是 SQLAlchemy 2.0 中与 Mapped[] 配合使用的新方式
    # 它允许将类型信息直接传递给 mapped_column

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        # server_default=func.now(), # 也可以考虑数据库级别默认值
        nullable=False
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        # server_default=func.now(),
        # server_onupdate=func.now(), # 也可以考虑数据库级别默认值和更新触发器
        nullable=False
    )

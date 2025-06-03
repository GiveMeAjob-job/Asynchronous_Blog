from sqlalchemy import Boolean, Column, Integer, String, DateTime
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.core.database import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = {'extend_existing': True}  # 确保这个参数对于您的用例是必要的

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)

    # 用于邮件验证的字段
    email_verification_token = Column(String, index=True, unique=True, nullable=True)  # token 通常应该是唯一的（或者在生成时保证唯一性）
    email_verification_token_expires_at = Column(DateTime(timezone=True), nullable=True)

    # 用于密码重置的字段
    password_reset_token = Column(String, index=True, unique=True, nullable=True)  # token 通常应该是唯一的
    password_reset_token_expires_at = Column(DateTime(timezone=True), nullable=True)

    # 其他字段
    is_active = Column(Boolean, default=True)
    is_superuser = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # 关系
    posts = relationship("Post", back_populates="author")
    comments = relationship("Comment", back_populates="author")

    # 移除下面这些重复的定义：
    # email_verification_token = Column(String, nullable=True)
    # email_verification_token_expires = Column(DateTime(timezone=True), nullable=True)
    # password_reset_token = Column(String, nullable=True)
    # password_reset_token_expires = Column(DateTime(timezone=True), nullable=True)

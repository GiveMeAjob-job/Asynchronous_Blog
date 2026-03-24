from datetime import datetime, timedelta
import secrets

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.models.mixins import TimestampMixin


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    username = Column(String(50), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)

    full_name = Column(String(100), nullable=True)
    bio = Column(Text, nullable=True)
    avatar_url = Column(String(500), nullable=True)
    website = Column(String(200), nullable=True)
    location = Column(String(100), nullable=True)

    is_active = Column(Boolean, default=True, nullable=False)
    is_superuser = Column(Boolean, default=False, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)

    email_verification_token = Column(String(255), unique=True, index=True, nullable=True)
    email_verification_token_expires_at = Column(DateTime(timezone=True), nullable=True)
    password_reset_token = Column(String(255), unique=True, index=True, nullable=True)
    password_reset_token_expires_at = Column(DateTime(timezone=True), nullable=True)

    post_count = Column(Integer, default=0, nullable=False)
    comment_count = Column(Integer, default=0, nullable=False)
    token_version = Column(Integer, default=0, nullable=False)

    posts = relationship("Post", back_populates="author", cascade="all, delete-orphan")
    comments = relationship("Comment", back_populates="author", cascade="all, delete-orphan")
    post_likes = relationship("PostLike", back_populates="user", cascade="all, delete-orphan")
    comment_likes = relationship("CommentLike", back_populates="user", cascade="all, delete-orphan")

    def generate_email_verification_token(self) -> str:
        self.email_verification_token = secrets.token_urlsafe(32)
        self.email_verification_token_expires_at = datetime.utcnow() + timedelta(hours=24)
        return self.email_verification_token

    def generate_password_reset_token(self) -> str:
        self.password_reset_token = secrets.token_urlsafe(32)
        self.password_reset_token_expires_at = datetime.utcnow() + timedelta(hours=1)
        return self.password_reset_token

    def verify_email(self) -> None:
        self.is_verified = True
        self.is_active = True
        self.email_verification_token = None
        self.email_verification_token_expires_at = None

    def bump_token_version(self) -> None:
        self.token_version = (self.token_version or 0) + 1

    def __repr__(self) -> str:
        return f"<User(id={self.id}, username='{self.username}', email='{self.email}')>"

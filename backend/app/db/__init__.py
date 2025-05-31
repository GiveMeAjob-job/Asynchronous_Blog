"""Database package initialization."""

# Alembic needs to import models and Base from another directory to avoid
# circular dependencies. This ensures that models are registered when
# Alembic runs migrations.
from app import models  # noqa: F401

from .base import Base

__all__ = ["Base"]

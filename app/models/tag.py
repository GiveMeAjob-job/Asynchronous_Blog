from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship
from app.core.database import Base
from .post import post_tag

class Tag(Base):
    __tablename__ = "tags"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)

    posts = relationship("Post", secondary=post_tag, back_populates="tags")

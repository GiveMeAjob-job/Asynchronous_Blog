from sqlalchemy import Column, Integer, String,Table, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base

post_tag = Table(
    "post_tag",
    Base.metadata,
    Column("post_id", Integer, ForeignKey("posts.id"), primary_key=True),
    Column("tag_id", Integer, ForeignKey("tags.id"), primary_key=True),
    extend_existing=True
)


class Tag(Base):
    __tablename__ = "tags"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)

    posts = relationship("Post", secondary=post_tag, back_populates="tags")

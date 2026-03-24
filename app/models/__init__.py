from app.models.category import Category
from app.models.comment import Comment
from app.models.like import CommentLike, PostLike
from app.models.post import Post
from app.models.tag import Tag, post_tag, post_tags
from app.models.user import User


def import_all():
    return User, Category, Tag, Post, post_tag, Comment


__all__ = [
    "User",
    "Category",
    "Tag",
    "Post",
    "post_tag",
    "post_tags",
    "Comment",
    "PostLike",
    "CommentLike",
    "import_all",
]

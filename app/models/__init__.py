# 导入所有模型
def import_all():
    from .user import User
    from .category import Category
    from .post import Post
    from .tag import Tag, post_tag
    from .comment import Comment

    return User, Category, Tag, Post, post_tag, Comment

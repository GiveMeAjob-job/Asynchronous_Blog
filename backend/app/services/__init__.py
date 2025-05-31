"""Service layer helpers and database accessors."""

from .deps import get_current_active_user, get_current_user, get_db
from .posts import (
    count_posts,
    create_post,
    delete_post,
    get_all_posts,
    get_post,
    get_posts_by_userid,
    update_post,
)
from .security import authenticate_user, create_access_token, get_hash_password
from .users import (
    create_user,
    get_user_by_email,
    get_user_by_id,
    get_user_by_username,
    get_users,
    update_user,
)

__all__ = [
    "authenticate_user",
    "create_access_token",
    "get_hash_password",
    "get_db",
    "get_current_user",
    "get_current_active_user",
    "create_user",
    "get_user_by_email",
    "get_user_by_id",
    "get_user_by_username",
    "get_users",
    "update_user",
    "create_post",
    "update_post",
    "delete_post",
    "count_posts",
    "get_all_posts",
    "get_post",
    "get_posts_by_userid",
]

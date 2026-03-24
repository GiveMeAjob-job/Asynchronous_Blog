"""sync application schema

Revision ID: b7fb5b66bab3
Revises: 55d73e06ef07
Create Date: 2026-03-24 02:52:45.378402
"""
from typing import Sequence, Union
import re
import unicodedata

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'b7fb5b66bab3'
down_revision: Union[str, None] = '55d73e06ef07'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _slugify(value: str | None, fallback: str, max_length: int) -> str:
    text = unicodedata.normalize("NFD", value or "")
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[-\s]+", "-", text).strip("-")
    if len(text) > max_length:
        text = text[:max_length].rsplit("-", 1)[0]
    return text or fallback


def _build_unique_slugs(connection: sa.Connection, table_name: str, fallback_prefix: str, max_length: int) -> None:
    rows = connection.execute(
        sa.text(f"SELECT id, name FROM {table_name} ORDER BY id")
    ).mappings()
    used: set[str] = set()

    for row in rows:
        base = _slugify(row["name"], f"{fallback_prefix}-{row['id']}", max_length=max_length)
        slug = base
        suffix = 1
        while slug in used:
            reserved = len(str(suffix)) + 1
            prefix = base[: max_length - reserved].rstrip("-") or fallback_prefix
            slug = f"{prefix}-{suffix}"
            suffix += 1
        used.add(slug)
        connection.execute(
            sa.text(f"UPDATE {table_name} SET slug = :slug WHERE id = :id"),
            {"slug": slug, "id": row["id"]},
        )


def upgrade() -> None:
    connection = op.get_bind()

    op.create_table('post_likes',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('post_id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['post_id'], ['posts.id'], name=op.f('fk_post_likes_post_id_posts')),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_post_likes_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_post_likes')),
    sa.UniqueConstraint('user_id', 'post_id', name='_user_post_like_uc')
    )
    op.create_index(op.f('ix_post_likes_id'), 'post_likes', ['id'], unique=False)
    op.create_table('comment_likes',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('comment_id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['comment_id'], ['comments.id'], name=op.f('fk_comment_likes_comment_id_comments')),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_comment_likes_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_comment_likes')),
    sa.UniqueConstraint('user_id', 'comment_id', name='_user_comment_like_uc')
    )
    op.create_index(op.f('ix_comment_likes_id'), 'comment_likes', ['id'], unique=False)
    op.add_column('categories', sa.Column('slug', sa.String(length=100), nullable=True))
    op.add_column('categories', sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False))
    op.add_column('categories', sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
    op.add_column('categories', sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
    _build_unique_slugs(connection, "categories", "category", 100)
    op.alter_column('categories', 'slug', existing_type=sa.String(length=100), nullable=False)
    op.create_index(op.f('ix_categories_slug'), 'categories', ['slug'], unique=True)
    op.add_column('comments', sa.Column('is_approved', sa.Boolean(), server_default=sa.text('true'), nullable=False))
    op.add_column('comments', sa.Column('is_edited', sa.Boolean(), server_default=sa.text('false'), nullable=False))
    connection.execute(
        sa.text(
            """
            UPDATE comments
            SET created_at = COALESCE(created_at, now()),
                updated_at = COALESCE(updated_at, created_at, now())
            """
        )
    )
    op.alter_column('comments', 'created_at',
               existing_type=postgresql.TIMESTAMP(timezone=True),
               nullable=False,
               existing_server_default=sa.text('now()'))
    op.alter_column('comments', 'updated_at',
               existing_type=postgresql.TIMESTAMP(timezone=True),
               nullable=False)
    op.drop_column('comments', 'likes')
    op.add_column('posts', sa.Column('summary', sa.Text(), nullable=True))
    op.add_column('posts', sa.Column('featured_image', sa.String(length=500), nullable=True))
    op.add_column('posts', sa.Column('published_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('posts', sa.Column('is_featured', sa.Boolean(), server_default=sa.text('false'), nullable=False))
    op.add_column('posts', sa.Column('allow_comments', sa.Boolean(), server_default=sa.text('true'), nullable=False))
    op.add_column('posts', sa.Column('meta_title', sa.String(length=200), nullable=True))
    op.add_column('posts', sa.Column('meta_description', sa.Text(), nullable=True))
    op.add_column('posts', sa.Column('meta_keywords', sa.String(length=500), nullable=True))
    op.add_column('posts', sa.Column('like_count', sa.Integer(), server_default=sa.text('0'), nullable=False))
    op.add_column('posts', sa.Column('comment_count', sa.Integer(), server_default=sa.text('0'), nullable=False))
    connection.execute(
        sa.text(
            """
            UPDATE posts
            SET published = COALESCE(published, false),
                views = COALESCE(views, 0),
                published_at = CASE
                    WHEN published IS TRUE AND published_at IS NULL THEN COALESCE(updated_at, created_at, now())
                    ELSE published_at
                END,
                like_count = 0,
                comment_count = COALESCE(
                    (SELECT COUNT(*) FROM comments WHERE comments.post_id = posts.id),
                    0
                ),
                created_at = COALESCE(created_at, now()),
                updated_at = COALESCE(updated_at, created_at, now())
            """
        )
    )
    op.alter_column('posts', 'published',
               existing_type=sa.BOOLEAN(),
               nullable=False)
    op.alter_column('posts', 'views',
               existing_type=sa.INTEGER(),
               nullable=False)
    op.alter_column('posts', 'created_at',
               existing_type=postgresql.TIMESTAMP(timezone=True),
               nullable=False,
               existing_server_default=sa.text('now()'))
    op.alter_column('posts', 'updated_at',
               existing_type=postgresql.TIMESTAMP(timezone=True),
               nullable=False)
    op.create_index(op.f('ix_posts_is_featured'), 'posts', ['is_featured'], unique=False)
    op.create_index(op.f('ix_posts_published'), 'posts', ['published'], unique=False)
    op.create_index(op.f('ix_posts_published_at'), 'posts', ['published_at'], unique=False)
    op.add_column('tags', sa.Column('slug', sa.String(length=255), nullable=True))
    op.add_column('tags', sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
    op.add_column('tags', sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
    _build_unique_slugs(connection, "tags", "tag", 255)
    op.alter_column('tags', 'slug', existing_type=sa.String(length=255), nullable=False)
    op.create_index(op.f('ix_tags_slug'), 'tags', ['slug'], unique=True)
    op.add_column('users', sa.Column('full_name', sa.String(length=100), nullable=True))
    op.add_column('users', sa.Column('bio', sa.Text(), nullable=True))
    op.add_column('users', sa.Column('avatar_url', sa.String(length=500), nullable=True))
    op.add_column('users', sa.Column('website', sa.String(length=200), nullable=True))
    op.add_column('users', sa.Column('location', sa.String(length=100), nullable=True))
    op.add_column('users', sa.Column('is_verified', sa.Boolean(), server_default=sa.text('false'), nullable=False))
    op.add_column('users', sa.Column('post_count', sa.Integer(), server_default=sa.text('0'), nullable=False))
    op.add_column('users', sa.Column('comment_count', sa.Integer(), server_default=sa.text('0'), nullable=False))
    connection.execute(
        sa.text(
            """
            UPDATE users
            SET is_active = COALESCE(is_active, false),
                is_superuser = COALESCE(is_superuser, false),
                post_count = COALESCE((SELECT COUNT(*) FROM posts WHERE posts.author_id = users.id), 0),
                comment_count = COALESCE((SELECT COUNT(*) FROM comments WHERE comments.author_id = users.id), 0),
                created_at = COALESCE(created_at, now()),
                updated_at = COALESCE(updated_at, created_at, now())
            """
        )
    )
    op.alter_column('users', 'is_active',
               existing_type=sa.BOOLEAN(),
               nullable=False)
    op.alter_column('users', 'is_superuser',
               existing_type=sa.BOOLEAN(),
               nullable=False)
    op.alter_column('users', 'created_at',
               existing_type=postgresql.TIMESTAMP(timezone=True),
               nullable=False,
               existing_server_default=sa.text('now()'))
    op.alter_column('users', 'updated_at',
               existing_type=postgresql.TIMESTAMP(timezone=True),
               nullable=False)


def downgrade() -> None:
    op.alter_column('users', 'updated_at',
               existing_type=postgresql.TIMESTAMP(timezone=True),
               nullable=True)
    op.alter_column('users', 'created_at',
               existing_type=postgresql.TIMESTAMP(timezone=True),
               nullable=True,
               existing_server_default=sa.text('now()'))
    op.alter_column('users', 'is_superuser',
               existing_type=sa.BOOLEAN(),
               nullable=True)
    op.alter_column('users', 'is_active',
               existing_type=sa.BOOLEAN(),
               nullable=True)
    op.drop_column('users', 'comment_count')
    op.drop_column('users', 'post_count')
    op.drop_column('users', 'is_verified')
    op.drop_column('users', 'location')
    op.drop_column('users', 'website')
    op.drop_column('users', 'avatar_url')
    op.drop_column('users', 'bio')
    op.drop_column('users', 'full_name')
    op.drop_index(op.f('ix_tags_slug'), table_name='tags')
    op.drop_column('tags', 'updated_at')
    op.drop_column('tags', 'created_at')
    op.drop_column('tags', 'slug')
    op.drop_index(op.f('ix_posts_published_at'), table_name='posts')
    op.drop_index(op.f('ix_posts_published'), table_name='posts')
    op.drop_index(op.f('ix_posts_is_featured'), table_name='posts')
    op.alter_column('posts', 'updated_at',
               existing_type=postgresql.TIMESTAMP(timezone=True),
               nullable=True)
    op.alter_column('posts', 'created_at',
               existing_type=postgresql.TIMESTAMP(timezone=True),
               nullable=True,
               existing_server_default=sa.text('now()'))
    op.alter_column('posts', 'views',
               existing_type=sa.INTEGER(),
               nullable=True)
    op.alter_column('posts', 'published',
               existing_type=sa.BOOLEAN(),
               nullable=True)
    op.drop_column('posts', 'comment_count')
    op.drop_column('posts', 'like_count')
    op.drop_column('posts', 'meta_keywords')
    op.drop_column('posts', 'meta_description')
    op.drop_column('posts', 'meta_title')
    op.drop_column('posts', 'allow_comments')
    op.drop_column('posts', 'is_featured')
    op.drop_column('posts', 'published_at')
    op.drop_column('posts', 'featured_image')
    op.drop_column('posts', 'summary')
    op.add_column('comments', sa.Column('likes', sa.INTEGER(), autoincrement=False, nullable=True))
    op.alter_column('comments', 'updated_at',
               existing_type=postgresql.TIMESTAMP(timezone=True),
               nullable=True)
    op.alter_column('comments', 'created_at',
               existing_type=postgresql.TIMESTAMP(timezone=True),
               nullable=True,
               existing_server_default=sa.text('now()'))
    op.drop_column('comments', 'is_edited')
    op.drop_column('comments', 'is_approved')
    op.drop_index(op.f('ix_categories_slug'), table_name='categories')
    op.drop_column('categories', 'updated_at')
    op.drop_column('categories', 'created_at')
    op.drop_column('categories', 'is_active')
    op.drop_column('categories', 'slug')
    op.drop_index(op.f('ix_comment_likes_id'), table_name='comment_likes')
    op.drop_table('comment_likes')
    op.drop_index(op.f('ix_post_likes_id'), table_name='post_likes')
    op.drop_table('post_likes')

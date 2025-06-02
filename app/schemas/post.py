# app/schemas/post.py
from typing import Optional, List, Any
from datetime import datetime
from pydantic import BaseModel, validator, Field # Added Field for potential future use
import re

# It's good practice to define related helper schemas first, or import them
# Assuming TagCreate is simple enough or already defined/imported if needed by PostCreate directly
# If TagCreate is more complex and defined in .tag, ensure that import is fine.
# from .tag import TagCreate # This was in your original file

# Define base schemas first
class TagBase(BaseModel):
    name: str

class TagCreate(TagBase): # Assuming TagCreate from this file
    pass

class Tag(TagBase):
    id: int

    class Config:
        from_attributes = True


class CategoryBase(BaseModel):
    name: str
    description: Optional[str] = None

class CategoryCreate(CategoryBase):
    pass

class Category(CategoryBase):
    id: int

    class Config:
        from_attributes = True


class CommentBase(BaseModel):
    content: str

class CommentCreate(CommentBase):
    post_id: int # Ensure this is expected by your API; your original PostCreate takes post_id

class Comment(CommentBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    author_id: int # Assuming author_id, not full author object here for basic schema
    post_id: int

    class Config:
        from_attributes = True

# NOW DEFINE PostBase
class PostBase(BaseModel):
    title: str
    content: str
    published: Optional[bool] = False
    category_id: Optional[int] = None


# THEN define PostCreate, inheriting from the now-defined PostBase
class PostCreate(PostBase):
    slug: Optional[str] = None
    # Ensure the 'tags' field is here, as your API (posts.py) uses post_in.tags
    tags: Optional[List[str]] = [] # List of tag names

    @validator('slug', pre=True, always=True)
    def generate_slug(cls, v, values):
        if 'title' in values and v is None or v == "": # Also generate if slug is empty string
            # Simple slug generation, can be made more robust
            slug = values['title'].lower()
            slug = re.sub(r'\s+', '-', slug) # Replace spaces with hyphens
            slug = re.sub(r'[^\w\-]', '', slug) # Remove non-alphanumeric (except hyphen)
            slug = re.sub(r'-+', '-', slug) # Replace multiple hyphens with single
            slug = slug.strip('-') # Remove leading/trailing hyphens
            return slug
        if v is not None: # If slug is provided, validate it
            slug = v.lower()
            slug = re.sub(r'\s+', '-', slug)
            slug = re.sub(r'[^\w\-]', '', slug)
            slug = re.sub(r'-+', '-', slug)
            return slug.strip('-')
        return v # Should not happen if title exists and slug is None/empty

class PostUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    published: Optional[bool] = None
    category_id: Optional[int] = None
    tags: Optional[List[str]] = None # Allow updating tags by name


class Post(PostBase):
    id: int
    slug: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    author_id: int # Or a User schema for detailed output
    tags: List[Tag] = [] # For displaying existing, fully formed Tag objects
    # category: Optional[Category] = None # Already handled by category_id in PostBase, but for output you might want the full object

    class Config:
        from_attributes = True


class PostDetail(Post):
    # Inherits fields from Post
    comments: List[Comment] = []
    # If you want the category object instead of just id in detail view:
    category: Optional[Category] = None # Add this if you want the full category object in PostDetail
    # author: Optional[UserSchema] # If you want full author details instead of just author_id

    class Config:
        from_attributes = True

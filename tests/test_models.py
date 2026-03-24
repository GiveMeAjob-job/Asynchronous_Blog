from app.models import import_all, post_tag
from app.schemas.post import PostCreate, PostUpdate


def test_model_exports_support_legacy_import_pattern():
    exported = import_all()
    assert len(exported) == 6
    assert post_tag.name == "post_tag"


def test_post_schemas_use_published_contract():
    post_create = PostCreate(title="Hello World", content="Body", published=True, tags=["Python"])
    post_update = PostUpdate(published=False)

    assert post_create.published is True
    assert post_create.tags == ["Python"]
    assert post_update.published is False

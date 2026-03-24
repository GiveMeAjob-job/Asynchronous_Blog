from app.core.config import settings

try:
    from celery import Celery
except ModuleNotFoundError:
    Celery = None


if Celery is None:
    celery_app = None
else:
    celery_app = Celery("worker", broker=settings.CELERY_BROKER_URL)

if celery_app is not None:
    celery_app.conf.task_routes = {
        "app.tasks.email.send_email": "email-queue",
        "app.tasks.posts.update_post_stats": "stats-queue",
    }

    celery_app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        enable_utc=True,
    )

# 确保这个文件导出 celery_app
__all__ = ['celery_app']

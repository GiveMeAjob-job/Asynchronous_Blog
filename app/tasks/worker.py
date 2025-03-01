from celery import Celery

from app.core.config import settings

celery_app = Celery("worker", broker=settings.RABBITMQ_URL)

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

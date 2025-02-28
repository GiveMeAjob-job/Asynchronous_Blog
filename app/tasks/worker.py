from celery import Celery

# from app.core.config import settings

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

# app/tasks/email.py
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from celery import shared_task


# from app.core.config import settings

@shared_task
def send_email(
        email_to: str,
        subject: str,
        html_content: str,
        text_content: str = None
):
    """异步发送邮件"""
    if not settings.MAIL_USERNAME or not settings.MAIL_PASSWORD:
        return

    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = settings.MAIL_FROM
    message["To"] = email_to

    if text_content:
        message.attach(MIMEText(text_content, "plain"))

    message.attach(MIMEText(html_content, "html"))

    with smtplib.SMTP(settings.MAIL_SERVER, settings.MAIL_PORT) as server:
        if settings.MAIL_TLS:
            server.starttls()
        if settings.MAIL_USERNAME and settings.MAIL_PASSWORD:
            server.login(settings.MAIL_USERNAME, settings.MAIL_PASSWORD)
        server.sendmail(settings.MAIL_FROM, email_to, message.as_string())

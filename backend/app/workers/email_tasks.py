from app.workers.tasks import celery_app


@celery_app.task(name="app.workers.email_tasks.send_email")
def send_email_task(payload: dict) -> dict:
    return payload

from app.workers.tasks import celery_app


@celery_app.task(name="app.workers.payment_tasks.process_payment_webhook")
def process_payment_webhook_task(payload: dict) -> dict:
    return payload

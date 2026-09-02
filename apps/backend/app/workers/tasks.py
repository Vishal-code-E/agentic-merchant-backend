"""
Background tasks (Celery). Configure broker/backend via redis_url in settings.
TODO(v1.2): from celery import Celery; celery_app = Celery("worker", broker=..., backend=...)
"""


async def run_campaign_graph_task(merchant_id: str, time_window: dict) -> None:
    """Enqueue/execute campaign_graph for a merchant over the given time window. TODO(v1.3)."""
    raise NotImplementedError

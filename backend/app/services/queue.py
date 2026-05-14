import logging
import uuid

from redis import Redis
from rq import Queue

from ..config import get_settings

log = logging.getLogger(__name__)

_settings = get_settings()
_redis = Redis.from_url(_settings.REDIS_URL)
_queue = Queue("audio", connection=_redis, default_timeout=60 * 60 * 12)


def enqueue_job(job_id: uuid.UUID) -> str:
    rq_job = _queue.enqueue(
        "app.tasks.process_audio_job",
        str(job_id),
        job_id=str(job_id),
        result_ttl=86400,
        failure_ttl=86400 * 7,
    )
    log.info("Enqueued audio job %s -> rq=%s", job_id, rq_job.id)
    return rq_job.id

from unittest.mock import Mock, patch

import pytest
from redis.exceptions import RedisError

from app.errors import AppError
from app.services.queue import enqueue_unique


def test_enqueue_unique_uses_stable_job_id_and_timeout() -> None:
    queue = Mock()
    with patch("app.services.queue.get_queue", return_value=queue):
        enqueue_unique("app.worker_jobs.parse_document_job", "entity-1", 123)
    queue.enqueue_call.assert_called_once_with(
        func="app.worker_jobs.parse_document_job",
        args=("entity-1",),
        job_id="entity-1",
        timeout=123,
        result_ttl=86400,
        failure_ttl=604800,
    )


def test_queue_failure_becomes_structured_error() -> None:
    queue = Mock()
    queue.enqueue_call.side_effect = RedisError("offline")
    with patch("app.services.queue.get_queue", return_value=queue), pytest.raises(AppError) as caught:
        enqueue_unique("job", "entity-1")
    assert caught.value.code == "QUEUE_UNAVAILABLE"
    assert caught.value.status_code == 503

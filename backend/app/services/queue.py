from redis import Redis
from rq import Queue
from redis.exceptions import RedisError
from app.errors import AppError
from app.config import get_settings

def get_queue() -> Queue:
    connection=Redis.from_url(get_settings().redis_url)
    return Queue("default",connection=connection)


def get_ui_actuator_queue() -> Queue:
    connection = Redis.from_url(get_settings().redis_url)
    return Queue("ui-actuator", connection=connection)

def enqueue_unique(function: str, entity_id: str, timeout: int = 300) -> None:
    try:
        get_queue().enqueue_call(func=function,args=(entity_id,),job_id=entity_id,timeout=timeout,result_ttl=86400,failure_ttl=604800)
    except RedisError as exc:
        raise AppError("QUEUE_UNAVAILABLE","任务队列暂不可用，请稍后重试",503) from exc


def enqueue_ui_actuator(function: str, entity_id: str, timeout: int = 900) -> None:
    try:
        get_ui_actuator_queue().enqueue_call(func=function, args=(entity_id,), job_id=f"ui:{entity_id}", timeout=timeout, result_ttl=86400, failure_ttl=604800)
    except RedisError as exc:
        raise AppError("QUEUE_UNAVAILABLE", "UI actuator 队列暂不可用，请稍后重试", 503) from exc

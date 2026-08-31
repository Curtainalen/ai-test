from redis import Redis
from rq import Queue, Worker

from app.config import get_settings


def main() -> None:
    connection = Redis.from_url(get_settings().redis_url)
    Worker([Queue("ui-actuator", connection=connection)], connection=connection).work(with_scheduler=False)


if __name__ == "__main__":
    main()

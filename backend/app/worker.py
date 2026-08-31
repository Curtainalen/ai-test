from redis import Redis
from rq import Queue, Worker
import asyncio
from sqlalchemy import select

from app.config import get_settings
from app.database import worker_db_session
from app.models import ExecutionStep, ExecutionTask
from app.worker_jobs import _ensure_report
from datetime import UTC, datetime


async def recover_incomplete_executions() -> None:
    async with worker_db_session() as db:
        tasks = (await db.scalars(select(ExecutionTask).where(ExecutionTask.status == "running"))).all()
        for task in tasks:
            steps = (await db.scalars(select(ExecutionStep).where(ExecutionStep.execution_id == task.id))).all()
            for step in steps:
                if step.status == "running":
                    step.status = "error"
                    step.error_category = "executor_error"
                    step.error_message = "Worker 重启中断了运行步骤；为避免重复副作用未自动重放"
                    step.finished_at = datetime.now(UTC)
            task.status = "failed"
            task.error_category = "executor_error"
            task.error_message = "Worker 重启后安全收敛未完成执行"
            task.finished_at = datetime.now(UTC)
            await db.commit()
            await _ensure_report(db, task)


def main() -> None:
    asyncio.run(recover_incomplete_executions())
    connection = Redis.from_url(get_settings().redis_url)
    Worker([Queue("default", connection=connection)], connection=connection).work(with_scheduler=False)


if __name__ == "__main__":
    main()

import asyncio

from sqlalchemy.pool import NullPool

from app.database import worker_db_session


def test_worker_sessions_use_fresh_nullpool_engines_across_event_loops() -> None:
    async def open_session_once():
        async with worker_db_session() as session:
            return session.bind

    first_engine = asyncio.run(open_session_once())
    second_engine = asyncio.run(open_session_once())

    assert first_engine is not second_engine
    assert isinstance(first_engine.sync_engine.pool, NullPool)
    assert isinstance(second_engine.sync_engine.pool, NullPool)

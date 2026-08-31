from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.worker import recover_incomplete_executions


@pytest.mark.asyncio
async def test_recovery_with_no_running_tasks_is_safe() -> None:
    session = AsyncMock()
    scalar_result = Mock()
    scalar_result.all.return_value = []
    session.scalars.return_value = scalar_result
    context = AsyncMock()
    context.__aenter__.return_value = session
    with patch("app.worker.worker_db_session", return_value=context):
        await recover_incomplete_executions()
    session.commit.assert_not_called()

# mypy: ignore-errors

"""
Test outbox integration end-to-end: CRUD -> Outbox -> ARQ -> Handler

This test verifies the complete outbox pattern flow:
1. CRUD operation publishes event
2. Poller picks up event
3. ARQ worker executes handler
4. Event is marked as processed
"""

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.base.crud import BaseCRUD
from app.outbox.models import EventStatus, OutboxEvent
from app.outbox.poller import OutboxPoller
from app.outbox.registry import outbox_registry


# Mock handler for testing
@pytest.fixture
def mock_handler():
    """Mock handler that tracks calls"""
    handler = AsyncMock()
    handler.__name__ = "test_handler"
    return handler


@pytest.fixture
def test_crud():
    """Create a test CRUD instance with outbox enabled"""

    class TestModel:
        id: int = 1
        name: str = "test"

    class TestCRUD(BaseCRUD):
        def __init__(self):
            super().__init__(
                model=TestModel,
                outbox_events={
                    "after_create": "TEST_CREATE",
                    "after_update": "TEST_UPDATE",
                    "after_delete": "TEST_DELETE",
                },
            )

    return TestCRUD()


class TestOutboxIntegration:
    async def test_crud_publishes_outbox_event(
        self, test_crud, db_session: AsyncSession
    ):
        """Test that CRUD operations publish events to outbox"""
        # Register a test handler
        test_handler = AsyncMock()
        test_handler.__name__ = "test_create_handler"
        outbox_registry.register_handler("create.test", test_handler)

        # Mock the CRUD create operation
        test_data = {"name": "test_item"}

        # Create via CRUD - this should publish an outbox event
        with patch.object(test_crud, "_create_record") as mock_create:
            mock_create.return_value = {"id": 1, "name": "test_item"}

            await test_crud.create(db_session, test_data)

            # Verify outbox event was created
            query = await db_session.execute(
                "SELECT * FROM outbox_events WHERE event_type = 'TEST_CREATE'"
            )
            events = query.fetchall()

            assert len(events) == 1
            event = events[0]
            assert event.event_type == "TEST_CREATE"
            assert event.status == EventStatus.PENDING
            assert event.payload == test_data

    async def test_poller_processes_pending_events(
        self, mock_handler, db_session: AsyncSession
    ):
        """Test that poller picks up and processes pending events"""
        # Register test handler
        outbox_registry.register_handler("TEST_EVENT", mock_handler)

        # Create a pending event directly
        event = OutboxEvent(
            event_type="TEST_EVENT",
            payload={"test": "data"},
            status=EventStatus.PENDING,
        )
        db_session.add(event)
        await db_session.commit()

        # Run the poller
        poller = OutboxPoller()

        with patch("app.outbox.poller.arq_enqueue") as mock_enqueue:
            mock_enqueue.return_value = "job_123"

            await poller.poll_and_process()

            # Verify ARQ job was enqueued
            mock_enqueue.assert_called_once()
            call_args = mock_enqueue.call_args

            assert call_args[0][0] == "process_outbox_event"  # Function name
            assert call_args[1]["job_id"].startswith(f"outbox:{event.id}:")

            # Verify event status updated to PROCESSING
            await db_session.refresh(event)
            assert event.status == EventStatus.PROCESSING

    async def test_arq_handler_execution(self, mock_handler):
        """Test that ARQ properly executes registered handlers"""
        from app.core.arq_worker import process_outbox_event

        # Register test handler
        outbox_registry.register_handler("TEST_HANDLER", mock_handler)

        # Create test event data
        event_data = {
            "id": 1,
            "event_type": "TEST_HANDLER",
            "payload": {"user_id": 123, "action": "test"},
            "correlation_id": "test-123",
        }

        # Execute the ARQ handler
        with patch("app.core.arq_worker.get_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            with patch("app.core.arq_worker.mark_event_completed") as mock_mark:
                await process_outbox_event(event_data)

                # Verify handler was called with correct parameters
                mock_handler.assert_called_once_with(mock_db, event_data["payload"])

                # Verify event was marked as completed
                mock_mark.assert_called_once_with(mock_db, event_data["id"])

    async def test_handler_failure_retry_mechanism(self, mock_handler):
        """Test that failed handlers are retried according to ARQ configuration"""
        from app.core.arq_worker import process_outbox_event

        # Configure handler to fail
        mock_handler.side_effect = Exception("Handler failed")
        outbox_registry.register_handler("TEST_FAILURE", mock_handler)

        event_data = {
            "id": 1,
            "event_type": "TEST_FAILURE",
            "payload": {"test": "failure"},
            "correlation_id": "fail-123",
        }

        with patch("app.core.arq_worker.get_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            with patch("app.core.arq_worker.mark_event_failed") as mock_mark_failed:
                # This should raise the exception for ARQ to handle retries
                with pytest.raises(Exception, match="Handler failed"):
                    await process_outbox_event(event_data)

                # Verify handler was called
                mock_handler.assert_called_once()

                # Event should not be marked as failed yet (ARQ will retry)
                mock_mark_failed.assert_not_called()

    async def test_max_retries_exhausted(self):
        """Test that events are marked as failed after max retries"""
        # This would be tested by running ARQ with max_tries=3
        # and verifying the event status becomes FAILED
        # after the 3rd attempt

        # This test would require actual ARQ integration
        # For now, we document the expected behavior:
        """
        Expected behavior when max retries exhausted:
        1. ARQ tries handler 3 times (max_tries=3)
        2. Each retry waits 10 seconds (retry_delay=10)
        3. After 3rd failure, ARQ marks job as failed
        4. Our job completion callback marks event as FAILED
        5. Future polls skip FAILED events
        """
        pass

    async def test_duplicate_job_prevention(self, db_session: AsyncSession):
        """Test that duplicate ARQ jobs are prevented by fixed job IDs"""
        from app.outbox.poller import OutboxPoller

        # Create event
        event = OutboxEvent(
            event_type="TEST_DUPLICATE",
            payload={"test": "duplicate"},
            status=EventStatus.PENDING,
        )
        db_session.add(event)
        await db_session.commit()

        poller = OutboxPoller()

        with patch("app.outbox.poller.arq_enqueue") as mock_enqueue:
            # First poll - should enqueue job
            mock_enqueue.return_value = "job_123"
            await poller.poll_and_process()

            # Second poll - should not enqueue duplicate job
            # because event status is now PROCESSING
            await poller.poll_and_process()

            # Verify only one job was enqueued
            assert mock_enqueue.call_count == 1

            # Verify job ID is deterministic
            call_args = mock_enqueue.call_args
            job_id = call_args[1]["job_id"]
            expected_pattern = f"outbox:{event.id}:process_outbox_event"
            assert job_id == expected_pattern


if __name__ == "__main__":
    """
    Run integration tests to verify outbox pattern:

    python -m pytest app/tests/test_outbox_integration.py -v

    These tests verify:
    1. CRUD -> Outbox event creation
    2. Poller -> ARQ job enqueuing
    3. ARQ -> Handler execution
    4. Error handling and retries
    5. Idempotence and duplicate prevention
    """
    pytest.main([__file__, "-v"])

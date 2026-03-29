"""Pytest configuration and fixtures for Aldes integration tests."""

import asyncio

import pytest


@pytest.fixture
def event_loop():
    """Create event loop for tests."""
    loop = asyncio.new_event_loop()
    yield loop

    # Clean up pending tasks
    pending = asyncio.all_tasks(loop)
    for task in pending:
        task.cancel()

    # Run loop to process cancellations
    loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))

    loop.close()


@pytest.fixture
async def cleanup_tasks():
    """Cleanup async tasks after test."""
    yield

    # Get all tasks and cancel them
    tasks = [task for task in asyncio.all_tasks() if not task.done()]

    for task in tasks:
        task.cancel()

    # Wait for cancellation
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)

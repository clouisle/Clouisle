from unittest.mock import patch

from main import start_sandbox_worker


def test_start_sandbox_worker_uses_solo_pool_by_default():
    with patch("main.start_worker") as mock_start_worker:
        start_sandbox_worker()

    mock_start_worker.assert_called_once_with(concurrency=1, queues="sandbox", pool="solo")


def test_start_sandbox_worker_keeps_prefork_for_higher_concurrency():
    with patch("main.start_worker") as mock_start_worker:
        start_sandbox_worker(concurrency=2)

    mock_start_worker.assert_called_once_with(concurrency=2, queues="sandbox", pool=None)

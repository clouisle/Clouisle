from datetime import UTC, datetime, timedelta

from uuid import uuid4

import pytest

from app.services.sandbox.models import (
    SandboxExecutionMetadata,
    SandboxTaskStatus,
    SandboxJob,
)


def test_sandbox_job_normalizes_legacy_input_file_content():
    job = SandboxJob(
        input_files=[
            {
                "target_path": "/workspace/input.txt",
                "content": "bGVnYWN5",
            }
        ]
    )

    assert job.input_files[0].content_base64 == "bGVnYWN5"


def test_sandbox_job_preserves_explicit_input_file_content_base64():
    job = SandboxJob(
        input_files=[
            {
                "target_path": "/workspace/input.txt",
                "content": "bGVnYWN5",
                "content_base64": "ZXhwbGljaXQ=",
            }
        ]
    )

    assert job.input_files[0].content_base64 == "ZXhwbGljaXQ="


def test_sandbox_job_accepts_asset_input_reference():
    asset_id = uuid4()
    job = SandboxJob(
        input_files=[
            {
                "target_path": "/workspace/input/report.pdf",
                "asset_id": asset_id,
                "expected_size": 12,
            }
        ]
    )

    assert job.input_files[0].asset_id == asset_id
    assert job.input_files[0].expected_size == 12


def test_sandbox_job_rejects_multiple_input_sources():
    with pytest.raises(ValueError, match="Exactly one Sandbox input source"):
        SandboxJob(
            input_files=[
                {
                    "target_path": "/workspace/input.txt",
                    "asset_id": uuid4(),
                    "content_base64": "bGVnYWN5",
                }
            ]
        )


def test_sandbox_job_rejects_missing_input_source():
    with pytest.raises(ValueError, match="Exactly one Sandbox input source"):
        SandboxJob(input_files=[{"target_path": "/workspace/input.txt"}])
    queued_at = datetime(2026, 1, 1, tzinfo=UTC)
    metadata = SandboxExecutionMetadata(queued_at=queued_at)

    metadata.mark_started(queued_at + timedelta(seconds=1))
    metadata.mark_prepare_started(queued_at + timedelta(seconds=2))
    metadata.mark_prepare_completed(queued_at + timedelta(seconds=3))
    metadata.mark_install_started(queued_at + timedelta(seconds=4))
    metadata.mark_install_completed(queued_at + timedelta(seconds=6))
    metadata.mark_execute_started(queued_at + timedelta(seconds=7))
    metadata.mark_execute_completed(queued_at + timedelta(seconds=10))
    metadata.mark_collect_started(queued_at + timedelta(seconds=11))
    metadata.mark_collect_completed(queued_at + timedelta(seconds=12))
    metadata.mark_completed(queued_at + timedelta(seconds=13))

    assert metadata.status == SandboxTaskStatus.COLLECTING
    assert metadata.stage is None
    assert metadata.queue_wait_ms == 1000
    assert metadata.prepare_ms == 1000
    assert metadata.install_ms == metadata.install_duration_ms == 2000
    assert metadata.execute_ms == 3000
    assert metadata.collect_ms == 1000
    assert metadata.total_ms == metadata.duration_ms == 13000


def test_sandbox_job_rejects_empty_command_argument():
    with pytest.raises(ValueError, match="command arguments must be non-empty"):
        SandboxJob(command=["python", ""])


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        (
            "python_package_index_url",
            " https://mirror.example.com/simple/ ",
            "https://mirror.example.com/simple",
        ),
        ("node_package_registry_url", "   ", None),
    ],
)
def test_sandbox_job_normalizes_package_source_urls(field, value, expected):
    assert getattr(SandboxJob(**{field: value}), field) == expected


@pytest.mark.parametrize(
    "field", ["python_package_index_url", "node_package_registry_url"]
)
def test_sandbox_job_rejects_non_string_package_source_url(field):
    with pytest.raises(ValueError, match="package source URL must be a string"):
        SandboxJob(**{field: 1})

import pytest

from app.services.sandbox.models import SandboxJob


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

import pytest

from app.schemas.model import validate_model_capabilities


@pytest.mark.parametrize(
    "legacy,expected", [(True, ["text", "image"]), (False, ["text"])]
)
def test_legacy_vision_migrates_without_mutating_input(legacy, expected):
    original = {"vision": legacy, "extension": {"enabled": True}}
    result = validate_model_capabilities(original)
    assert result == {"input_modalities": expected, "extension": {"enabled": True}}
    assert original["vision"] is legacy


def test_explicit_modalities_override_legacy_vision():
    assert validate_model_capabilities(
        {"vision": True, "input_modalities": ["text"]}
    ) == {"input_modalities": ["text"]}
    assert validate_model_capabilities(None) is None
    assert validate_model_capabilities({"vision": "true"}) == {}


@pytest.mark.parametrize("key", ["input_modalities", "output_modalities"])
@pytest.mark.parametrize("value", [None, "image", ["unknown"], [1]])
def test_rejects_invalid_modality_declarations(key, value):
    with pytest.raises(ValueError, match=key):
        validate_model_capabilities({key: value})


@pytest.mark.parametrize(
    "limits,reason",
    [
        ([], "input_limits must be an object"),
        ({"unknown": {}}, "unsupported modality"),
        ({"image": []}, "must be an object"),
        ({"image": {"max_bytes": True}}, "positive integer"),
        ({"image": {"max_bytes": 0}}, "positive integer"),
        ({"image": {"max_bytes": -1}}, "positive integer"),
        ({"image": {"max_bytes": "1024"}}, "positive integer"),
        ({"image": {"mime_types": "image/png"}}, "valid MIME types"),
        ({"image": {"mime_types": [1]}}, "valid MIME types"),
        ({"image": {"mime_types": ["image"]}}, "valid MIME types"),
    ],
)
def test_rejects_invalid_input_limits(limits, reason):
    with pytest.raises(ValueError, match=reason):
        validate_model_capabilities({"input_limits": limits})


def test_preserves_valid_limits_and_all_supported_modalities():
    capabilities = {
        "input_modalities": ["text", "image", "audio", "video", "file"],
        "output_modalities": [],
        "input_limits": {
            "image": {"max_bytes": 1024, "mime_types": ["image/png", "image/svg+xml"]},
            "audio": {"max_bytes": None, "mime_types": None},
            "file": {},
        },
    }
    assert validate_model_capabilities(capabilities) == capabilities


def test_rejects_non_object_capabilities():
    with pytest.raises(ValueError, match="capabilities must be an object"):
        validate_model_capabilities([])

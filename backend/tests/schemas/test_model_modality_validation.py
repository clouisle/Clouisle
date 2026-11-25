import pytest

from app.schemas.model import ModelType, validate_model_capabilities


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


def test_every_model_type_declares_its_modalities():
    """A type added without a table entry would silently skip validation."""
    from app.schemas.model import _MODEL_TYPE_MODALITIES

    assert {member.value for member in ModelType} == set(_MODEL_TYPE_MODALITIES)


@pytest.mark.parametrize(
    "capabilities,reason",
    [
        ({"input_modalities": ["text"]}, "input_modalities cannot declare text"),
        ({"output_modalities": ["image"]}, "output_modalities cannot declare image"),
        ({"output_modalities": ["text", "video"]}, "cannot declare video"),
    ],
)
def test_ocr_rejects_modalities_it_cannot_accept(capabilities, reason):
    with pytest.raises(ValueError, match=reason):
        validate_model_capabilities(capabilities, ModelType.OCR)


def test_ocr_accepts_an_image_or_document_and_text_output():
    capabilities = {
        "input_modalities": ["image", "file"],
        "output_modalities": ["text"],
    }
    assert validate_model_capabilities(capabilities, ModelType.OCR) == capabilities


def test_chat_keeps_every_multimodal_declaration():
    capabilities = {
        "input_modalities": ["text", "image", "audio", "video", "file"],
        "output_modalities": ["text", "image"],
    }
    assert validate_model_capabilities(capabilities, ModelType.CHAT) == capabilities


@pytest.mark.parametrize(
    "model_type,capabilities",
    [
        (ModelType.TEXT_TO_IMAGE, {"output_modalities": ["image"]}),
        (ModelType.TEXT_TO_VIDEO, {"output_modalities": ["video"]}),
        (ModelType.TTS, {"output_modalities": ["audio"]}),
        (ModelType.STT, {"input_modalities": ["audio"]}),
    ],
)
def test_generation_types_validate_against_their_own_shape(model_type, capabilities):
    assert validate_model_capabilities(capabilities, model_type) == capabilities


@pytest.mark.parametrize(
    "model_type", [ModelType.EMBEDDING, ModelType.RERANK, ModelType.DECISION]
)
def test_vector_and_score_types_declare_no_output_modality(model_type):
    assert validate_model_capabilities({"output_modalities": []}, model_type) == {
        "output_modalities": []
    }
    with pytest.raises(ValueError, match="output_modalities cannot declare text"):
        validate_model_capabilities({"output_modalities": ["text"]}, model_type)


def test_input_limits_must_belong_to_an_input_modality_of_the_type():
    with pytest.raises(ValueError, match="input_limits.text is not an input modality"):
        validate_model_capabilities({"input_limits": {"text": {}}}, ModelType.OCR)
    assert validate_model_capabilities(
        {"input_limits": {"image": {"max_bytes": 1024}}}, ModelType.OCR
    ) == {"input_limits": {"image": {"max_bytes": 1024}}}


def test_omitting_the_model_type_keeps_vocabulary_only_validation():
    capabilities = {"output_modalities": ["image"]}
    assert validate_model_capabilities(capabilities) == capabilities

import base64
import io

from PIL import Image

from app.services import chat_context


def _encoded_image(mode: str, size: tuple[int, int] = (2, 2)) -> str:
    source = io.BytesIO()
    image = Image.new(mode, size)
    image.save(source, format="PNG")
    return base64.b64encode(source.getvalue()).decode()


def test_normalize_vision_image_keeps_small_images_and_handles_non_alpha_modes():
    small = _encoded_image("RGB")
    normalized, image_format = chat_context._normalize_vision_image(small, "png")

    assert normalized == small
    assert image_format == "png"

    palette = _encoded_image("P", (3000, 2))
    normalized_palette, normalized_format = chat_context._normalize_vision_image(
        palette,
        "png",
    )

    assert normalized_format == "jpeg"
    with Image.open(io.BytesIO(base64.b64decode(normalized_palette))) as image:
        assert image.mode == "RGB"
        assert max(image.size) <= 2048

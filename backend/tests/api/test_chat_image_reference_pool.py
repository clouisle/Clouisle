import json
from types import SimpleNamespace
from uuid import uuid4

from app.api.v1.endpoints.chat_helpers.general import (
    append_conversation_image_inventory,
    append_generated_images,
    collect_conversation_images,
)
from app.models.agent import MessageRole


def _message(role, content="", images=None):
    return SimpleNamespace(
        id=uuid4(),
        role=role,
        content=content,
        images=images or [],
    )


def test_collects_conversation_images_in_chronological_order():
    current = _message(
        MessageRole.USER,
        "Use current",
        [{"url": "data:image/png;base64,Y3VycmVudA=="}],
    )
    messages = [
        _message(
            MessageRole.USER,
            "Earlier upload",
            [{"url": "data:image/png;base64,dXBsb2Fk"}],
        ),
        _message(
            MessageRole.TOOL,
            json.dumps(
                {
                    "kind": "media.image",
                    "success": True,
                    "prompt": "Earlier generation",
                    "images": [
                        {
                            "image": {
                                "url": "/api/v1/upload/files/generated-images/out.png"
                            }
                        }
                    ],
                }
            ),
        ),
        current,
    ]

    images, inventory = collect_conversation_images(
        messages,
        current_message_id=current.id,
        current_images=current.images,
    )

    assert [image["url"] for image in images] == [
        "data:image/png;base64,dXBsb2Fk",
        "/api/v1/upload/files/generated-images/out.png",
        "data:image/png;base64,Y3VycmVudA==",
    ]
    assert [item["origin"] for item in inventory] == [
        "uploaded",
        "generated",
        "uploaded",
    ]


def test_generated_images_append_and_inventory_omits_sources():
    images = []
    inventory = []
    append_generated_images(
        images,
        inventory,
        {
            "kind": "media.image",
            "success": True,
            "prompt": "A generated reference",
            "images": [
                {
                    "image": {
                        "url": "/api/v1/upload/files/generated-images/out.png",
                        "base64": "secret-payload",
                    }
                }
            ],
        },
    )

    message = append_conversation_image_inventory("Continue", inventory)

    assert len(images) == 1
    assert "1. generated: A generated reference" in message
    assert "secret-payload" not in message
    assert "/api/v1/upload/files" not in message


def test_ignores_failed_malformed_and_source_less_results():
    images = []
    inventory = []
    for result in (
        "not json",
        {"kind": "media.image", "success": False, "images": []},
        {"kind": "other", "success": True, "images": []},
        {
            "kind": "media.image",
            "success": True,
            "images": [{"image": {}}],
        },
    ):
        append_generated_images(images, inventory, result)

    assert images == []
    assert inventory == []

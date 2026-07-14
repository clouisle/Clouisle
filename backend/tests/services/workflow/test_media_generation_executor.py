from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.workflow.executors.media_generation import MediaGenerationNodeExecutor


class TestMediaGenerationNodeExecutor:
    @pytest.mark.anyio
    async def test_execute_image_resolves_reference_image_and_model(self):
        executor = MediaGenerationNodeExecutor()
        node = {
            "id": "media_1",
            "type": "media_generation",
            "data": {
                "mediaGenerationConfig": {
                    "mode": "image",
                    "modelId": "team-model-1",
                    "prompt": "make {{start.topic}}",
                    "referenceImageVariable": "{{upload.image}}",
                    "outputVariable": "imageResult",
                }
            },
        }
        context = MagicMock()
        context.resolve_variable_ref = AsyncMock(
            side_effect=["a cat", {"base64": "cmVm", "format": "png"}]
        )
        team_model = SimpleNamespace(model=SimpleNamespace(id="model-1"))

        with (
            patch("app.models.model.TeamModel.filter") as mock_team_model_filter,
            patch(
                "app.services.workflow.executors.media_generation.generate_image",
                new=AsyncMock(
                    return_value={
                        "display_result": {
                            "kind": "media.image",
                            "success": True,
                            "prompt": "make a cat",
                            "images": [],
                            "error": None,
                        },
                        "llm_result": "ok",
                    }
                ),
            ) as mock_generate_image,
        ):
            mock_team_model_filter.return_value.prefetch_related.return_value.first = (
                AsyncMock(return_value=team_model)
            )

            result = await executor.execute(node, context, MagicMock())

        assert result.success is True
        assert result.outputs["result"]["kind"] == "media.image"
        assert result.outputs["imageResult"]["kind"] == "media.image"
        mock_generate_image.assert_awaited_once()
        kwargs = mock_generate_image.await_args.kwargs
        assert kwargs["prompt"] == "make a cat"
        assert kwargs["images"] == [{"base64": "cmVm", "format": "png"}]
        assert kwargs["agent"].image_generation_config["default_model_ref"] == "model-1"

    @pytest.mark.anyio
    async def test_execute_video_passes_start_image_as_current_image(self):
        executor = MediaGenerationNodeExecutor()
        node = {
            "id": "media_2",
            "type": "media_generation",
            "data": {
                "mediaGenerationConfig": {
                    "mode": "video",
                    "modelId": "model-1",
                    "prompt": "animate",
                    "startImageVariable": "{{image.result}}",
                }
            },
        }
        context = MagicMock()
        context.resolve_variable_ref = AsyncMock(return_value={"url": "https://x.test/a.png"})
        model = SimpleNamespace(id="model-1")

        with (
            patch("app.models.model.TeamModel.filter") as mock_team_model_filter,
            patch("app.models.model.Model.filter") as mock_model_filter,
            patch(
                "app.services.workflow.executors.media_generation.generate_video",
                new=AsyncMock(
                    return_value={
                        "display_result": {
                            "kind": "media.video",
                            "success": True,
                            "prompt": "animate",
                            "status": "completed",
                            "video": None,
                            "error": None,
                        },
                        "llm_result": "ok",
                    }
                ),
            ) as mock_generate_video,
        ):
            mock_team_model_filter.return_value.prefetch_related.return_value.first = (
                AsyncMock(return_value=None)
            )
            mock_model_filter.return_value.first = AsyncMock(return_value=model)

            result = await executor.execute(node, context, MagicMock())

        assert result.success is True
        mock_generate_video.assert_awaited_once()
        kwargs = mock_generate_video.await_args.kwargs
        assert kwargs["start_image_index"] == 1
        assert kwargs["current_images"] == [{"url": "https://x.test/a.png"}]
        assert kwargs["agent"].video_generation_config["default_model_ref"] == "model-1"

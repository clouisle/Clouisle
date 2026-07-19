from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.workflow.executors.media_generation import MediaGenerationNodeExecutor


class TestMediaGenerationNodeExecutor:
    @pytest.mark.anyio
    @pytest.mark.parametrize(
        ("config", "expected_error"),
        [
            (
                {"mode": "audio", "modelId": "model-1", "prompt": "create"},
                "workflow_media_invalid_mode",
            ),
            (
                {"mode": "image", "modelId": "model-1", "prompt": ""},
                "workflow_media_prompt_required",
            ),
            (
                {"mode": "image", "prompt": "create"},
                "workflow_media_model_required",
            ),
        ],
    )
    async def test_execute_returns_actionable_configuration_error(
        self, config, expected_error
    ):
        result = await MediaGenerationNodeExecutor().execute(
            {
                "id": "media_1",
                "data": {"mediaGenerationConfig": config},
            },
            MagicMock(),
            MagicMock(),
        )

        assert result.error == expected_error

    @pytest.mark.anyio
    async def test_execute_returns_actionable_error_when_model_no_longer_exists(self):
        context = MagicMock()
        with (
            patch("app.models.workflow.Workflow.filter") as mock_workflow_filter,
            patch("app.models.model.TeamModel.filter") as mock_team_model_filter,
        ):
            mock_workflow_filter.return_value.only.return_value.first = AsyncMock(
                return_value=SimpleNamespace(team_id="team-1")
            )
            mock_team_model_filter.return_value.prefetch_related.return_value.first = (
                AsyncMock(return_value=None)
            )

            result = await MediaGenerationNodeExecutor().execute(
                {
                    "id": "media_1",
                    "data": {
                        "mediaGenerationConfig": {
                            "mode": "image",
                            "modelId": "deleted-model",
                            "prompt": "create",
                        }
                    },
                },
                context,
                MagicMock(),
            )

        assert result.error == "workflow_media_model_not_found"

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
            patch("app.models.workflow.Workflow.filter") as mock_workflow_filter,
            patch("app.models.model.TeamModel.filter") as mock_team_model_filter,
            patch(
                "app.services.workflow.executors.media_generation.generate_image",
                new=AsyncMock(
                    return_value={
                        "display_result": {
                            "kind": "media.image",
                            "success": True,
                            "prompt": "make a cat",
                            "images": [
                                {
                                    "image": {
                                        "url": "/api/v1/upload/files/generated-images/a.png"
                                    }
                                },
                                {
                                    "image": {
                                        "url": "/api/v1/upload/files/generated-images/b.png"
                                    }
                                },
                            ],
                            "error": None,
                        },
                        "llm_result": "ok",
                    }
                ),
            ) as mock_generate_image,
        ):
            mock_workflow_filter.return_value.only.return_value.first = AsyncMock(
                return_value=SimpleNamespace(team_id="team-1")
            )
            mock_team_model_filter.return_value.prefetch_related.return_value.first = (
                AsyncMock(return_value=team_model)
            )

            result = await executor.execute(
                node, context, SimpleNamespace(workflow_id="workflow-1")
            )

        assert result.success is True
        expected_urls = [
            "/api/v1/upload/files/generated-images/a.png",
            "/api/v1/upload/files/generated-images/b.png",
        ]
        assert result.outputs == {
            "result": expected_urls,
            "imageResult": expected_urls,
        }
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
        context.resolve_variable_ref = AsyncMock(
            return_value={"url": "https://x.test/a.png"}
        )
        team_model = SimpleNamespace(model=SimpleNamespace(id="model-1"))

        with (
            patch("app.models.workflow.Workflow.filter") as mock_workflow_filter,
            patch("app.models.model.TeamModel.filter") as mock_team_model_filter,
            patch(
                "app.services.workflow.executors.media_generation.generate_video",
                new=AsyncMock(
                    return_value={
                        "display_result": {
                            "kind": "media.video",
                            "success": True,
                            "prompt": "animate",
                            "status": "completed",
                            "video": {
                                "url": "/api/v1/upload/files/generated-videos/a.mp4"
                            },
                            "error": None,
                        },
                        "llm_result": "ok",
                    }
                ),
            ) as mock_generate_video,
        ):
            mock_workflow_filter.return_value.only.return_value.first = AsyncMock(
                return_value=SimpleNamespace(team_id="team-1")
            )
            mock_team_model_filter.return_value.prefetch_related.return_value.first = (
                AsyncMock(return_value=team_model)
            )

            result = await executor.execute(
                node, context, SimpleNamespace(workflow_id="workflow-1")
            )

        assert result.success is True
        assert result.outputs == {
            "result": "/api/v1/upload/files/generated-videos/a.mp4"
        }
        mock_generate_video.assert_awaited_once()
        kwargs = mock_generate_video.await_args.kwargs
        assert kwargs["start_image_index"] == 1
        assert kwargs["current_images"] == [{"url": "https://x.test/a.png"}]
        assert kwargs["agent"].video_generation_config["default_model_ref"] == "model-1"

    def test_video_output_alias_contains_only_url(self):
        result = MediaGenerationNodeExecutor()._to_execution_result(
            {
                "display_result": {
                    "success": True,
                    "video": {"url": "/api/v1/upload/files/generated-videos/a.mp4"},
                    "status": "completed",
                },
                "llm_result": "not exposed",
            },
            {"mode": "video", "outputVariable": "videoResult"},
        )

        assert result.outputs == {
            "result": "/api/v1/upload/files/generated-videos/a.mp4",
            "videoResult": "/api/v1/upload/files/generated-videos/a.mp4",
        }

    @pytest.mark.parametrize(
        ("tool_result", "config"),
        [
            ({"display_result": {"success": True, "images": []}}, {"mode": "image"}),
            ({"display_result": {"success": True, "video": {}}}, {"mode": "video"}),
            (
                {
                    "display_result": {
                        "success": False,
                        "error": "provider_failed",
                        "images": [{"image": {"url": "https://example.test/a.png"}}],
                    }
                },
                {"mode": "image"},
            ),
        ],
    )
    def test_invalid_media_result_does_not_publish_outputs(self, tool_result, config):
        result = MediaGenerationNodeExecutor()._to_execution_result(tool_result, config)

        assert result.success is False
        assert result.outputs == {}

    @pytest.mark.anyio
    async def test_validate_config_reports_each_missing_requirement(self):
        executor = MediaGenerationNodeExecutor()

        assert await executor.validate_config({}) == [
            "Model ID is required",
            "Prompt or inputs are required",
        ]
        assert await executor.validate_config(
            {"mode": "audio", "modelId": "model-1", "inputs": [{}]}
        ) == ["Invalid media generation mode"]
        assert (
            await executor.validate_config(
                {"mode": "video", "modelId": "model-1", "prompt": "animate"}
            )
            == []
        )

    @pytest.mark.anyio
    async def test_build_prompt_resolves_template_and_input_mappings(self):
        context = MagicMock()
        context.resolve_variable_ref = AsyncMock(side_effect=["cats", None, 3])

        prompt = await MediaGenerationNodeExecutor()._build_prompt(
            {
                "prompt": "Draw {{start.subject}} and {{missing.value}}",
                "inputs": [
                    {
                        "name": "count",
                        "source": "variable",
                        "variableRef": "{{start.count}}",
                    },
                    {"name": "style", "source": "constant", "constantValue": "ink"},
                ],
            },
            context,
        )

        assert prompt == ("count: 3\nstyle: ink\n\nDraw cats and {{missing.value}}")

    @pytest.mark.anyio
    async def test_image_dispatch_maps_optional_and_legacy_config(self):
        context = MagicMock()
        context.resolve_variable_ref = AsyncMock(return_value=None)
        with patch(
            "app.services.workflow.executors.media_generation.generate_image",
            new=AsyncMock(return_value={}),
        ) as generate:
            await MediaGenerationNodeExecutor()._execute_image(
                {
                    "width": "1024",
                    "height": 768,
                    "num_images": "2",
                    "negative_prompt": "blur",
                    "seed": "7",
                    "extra_params": {"steps": 20},
                },
                context,
                "draw",
                "model-1",
            )

        generate.assert_awaited_once()
        assert generate.await_args.kwargs == {
            "prompt": "draw",
            "width": 1024,
            "height": 768,
            "num_images": 2,
            "style": None,
            "quality": None,
            "negative_prompt": "blur",
            "seed": 7,
            "images": None,
            "extra_params": {"steps": 20},
            "agent": generate.await_args.kwargs["agent"],
        }

    @pytest.mark.anyio
    async def test_execute_translates_resolution_errors(self):
        executor = MediaGenerationNodeExecutor()
        executor._resolve_model_id = AsyncMock(side_effect=RuntimeError("secret"))
        with patch(
            "app.services.workflow.executors.media_generation.translate_public_workflow_error",
            return_value="workflow_execution_failed",
        ) as translate:
            result = await executor.execute(
                {
                    "id": "media_1",
                    "data": {
                        "config": {
                            "mode": "image",
                            "modelId": "model-1",
                            "inputs": [
                                {
                                    "name": "subject",
                                    "source": "constant",
                                    "constantValue": "cat",
                                }
                            ],
                        }
                    },
                },
                MagicMock(),
                SimpleNamespace(workflow_id="workflow-1"),
            )

        assert result.error == "workflow_execution_failed"
        translate.assert_called_once()

    @pytest.mark.parametrize(
        ("config", "expected_variables", "expected_kind", "expected_item_kind"),
        [
            ({}, [{"name": "result", "type": "array"}], "array", "string"),
            (
                {"mode": "video", "outputVariable": "clip"},
                [
                    {"name": "result", "type": "string"},
                    {"name": "clip", "type": "string"},
                ],
                "string",
                None,
            ),
        ],
    )
    def test_output_declarations_match_media_mode(
        self, config, expected_variables, expected_kind, expected_item_kind
    ):
        executor = MediaGenerationNodeExecutor()

        assert executor.get_output_variables(config) == expected_variables
        specs = executor.get_output_specs(config)
        assert [spec.name for spec in specs] == [
            item["name"] for item in expected_variables
        ]
        assert all(spec.type.kind == expected_kind for spec in specs)
        assert all(
            (spec.type.item.kind if spec.type.item else None) == expected_item_kind
            for spec in specs
        )

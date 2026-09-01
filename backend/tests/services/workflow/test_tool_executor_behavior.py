"""Behavioral tests for agent and HTTP workflow executors."""

import json
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call, patch

import httpx
import pytest

from app.services.workflow.executors.tool import (
    AgentNodeExecutor,
    HTTPRequestNodeExecutor,
)


@pytest.fixture
def context():
    value_by_ref = {
        "{{start.message}}": "hello",
        "{{start.token}}": "secret",
        "{{start.id}}": 42,
    }
    context = MagicMock(run_id="run-1")
    context.resolve_variable_ref = AsyncMock(side_effect=value_by_ref.get)
    return context


@pytest.fixture
def run():
    run = MagicMock(triggered_by_id="user-1")
    run.fetch_related = AsyncMock()
    run.triggered_by = MagicMock(locale="en")
    return run


@pytest.fixture
def agent_service(monkeypatch):
    service = MagicMock()
    module = ModuleType("app.services.agent")
    module.AgentService = MagicMock(return_value=service)
    monkeypatch.setitem(sys.modules, "app.services.agent", module)
    return service


class TestAgentNodeExecutorBehavior:
    @pytest.mark.anyio
    async def test_execute_rejects_missing_or_unknown_agent(
        self, context, run, agent_service
    ):
        executor = AgentNodeExecutor()

        missing_id = await executor.execute({"data": {"agentConfig": {}}}, context, run)

        with patch("app.models.agent.Agent.filter") as agent_filter:
            agent_filter.return_value.first = AsyncMock(return_value=None)
            unknown = await executor.execute(
                {"data": {"config": {"agentId": "missing"}}}, context, run
            )

        assert missing_id.error == "validation_error"
        assert unknown.error == "agent_not_found"

    @pytest.mark.anyio
    async def test_streaming_collects_chunks_and_publishes_only_text(
        self, context, run, agent_service
    ):
        agent = MagicMock()

        async def chat_stream(**kwargs):
            assert kwargs["message"] == "Ask hello / {{unknown}}"
            assert kwargs["context"] == {"token": "secret"}
            assert kwargs["user_id"] == "user-1"
            assert kwargs["max_turns"] == 3
            for chunk in (
                "first ",
                {"tool_call": {"name": "search"}},
                {"usage": {"tokens": 7}},
                "second",
            ):
                yield chunk

        node = {
            "id": "agent-node",
            "data": {
                "agentConfig": {
                    "agentId": "agent-1",
                    "message": "Ask {{start.message}} / {{unknown}}",
                    "context": [
                        {
                            "name": "token",
                            "source": "variable",
                            "variableRef": "{{start.token}}",
                        }
                    ],
                    "stream": True,
                    "maxTurns": 3,
                }
            },
        }

        agent_service.chat_stream = chat_stream
        with (
            patch("app.models.agent.Agent.filter") as agent_filter,
            patch(
                "app.services.workflow.executors.tool.StreamManager.publish_token",
                new=AsyncMock(),
            ) as publish_token,
        ):
            agent_filter.return_value.first = AsyncMock(return_value=agent)
            result = await AgentNodeExecutor().execute(node, context, run)

        assert result.outputs == {
            "response": "first second",
            "toolCalls": [{"name": "search"}],
            "usage": {"tokens": 7},
            "dialogue": [{"role": "assistant", "tool_calls": [{"name": "search"}]}],
            "artifacts": [],
        }
        assert publish_token.await_args_list == [
            call("agent-node", "first "),
            call("agent-node", "second"),
        ]

    @pytest.mark.anyio
    async def test_non_streaming_normalizes_missing_response_fields(
        self, context, agent_service
    ):
        run = MagicMock(triggered_by_id=None)
        agent = MagicMock()
        node = {
            "data": {
                "config": {
                    "agentId": "agent-1",
                    "message": "plain",
                    "stream": False,
                }
            }
        }

        agent_service.chat = AsyncMock(return_value={})
        with patch("app.models.agent.Agent.filter") as agent_filter:
            agent_filter.return_value.first = AsyncMock(return_value=agent)
            result = await AgentNodeExecutor().execute(node, context, run)

        assert result.outputs == {
            "response": "",
            "toolCalls": [],
            "usage": {},
            "dialogue": [],
            "artifacts": [],
        }
        agent_service.chat.assert_awaited_once_with(
            agent=agent,
            message="plain",
            context={},
            images=None,
            files=None,
            user_id=None,
            max_turns=10,
            user_locale="en",
        )

    @pytest.mark.anyio
    async def test_reserved_output_alias_preserves_structured_outputs(
        self, context, run, agent_service
    ):
        agent = MagicMock()
        agent_service.chat = AsyncMock(
            return_value={
                "response": "Done",
                "tool_calls": [{"id": "call-1"}],
                "usage": {"total_tokens": 4},
                "dialogue": [{"role": "assistant", "content": "Done"}],
                "artifacts": [{"url": "https://example.test/output.csv"}],
            }
        )
        node = {
            "data": {
                "config": {
                    "agentId": "agent-1",
                    "outputVariable": "toolCalls",
                    "stream": False,
                }
            }
        }

        with patch("app.models.agent.Agent.filter") as agent_filter:
            agent_filter.return_value.first = AsyncMock(return_value=agent)
            result = await AgentNodeExecutor().execute(node, context, run)

        assert result.outputs == {
            "response": "Done",
            "toolCalls": [{"id": "call-1"}],
            "usage": {"total_tokens": 4},
            "dialogue": [{"role": "assistant", "content": "Done"}],
            "artifacts": [{"url": "https://example.test/output.csv"}],
        }
        for output_var in ("response", "toolCalls", "usage", "dialogue", "artifacts"):
            assert [
                item["name"]
                for item in AgentNodeExecutor().get_output_variables(
                    {"outputVariable": output_var}
                )
            ] == ["response", "toolCalls", "usage", "dialogue", "artifacts"]

    @pytest.mark.anyio
    async def test_service_failure_is_translated(self, context, run, agent_service):
        agent_service.chat = AsyncMock(side_effect=RuntimeError("private detail"))
        with (
            patch("app.models.agent.Agent.filter") as agent_filter,
            patch(
                "app.services.workflow.executors.tool.translate_public_workflow_error",
                return_value="public_error",
            ) as translate,
        ):
            agent_filter.return_value.first = AsyncMock(return_value=MagicMock())
            result = await AgentNodeExecutor().execute(
                {"data": {"config": {"agentId": "agent-1", "stream": False}}},
                context,
                run,
            )

        assert result.error == "public_error"
        translate.assert_called_once()

    def test_output_metadata(self):
        executor = AgentNodeExecutor()

        assert [item["name"] for item in executor.get_output_variables({})] == [
            "response",
            "toolCalls",
            "usage",
            "dialogue",
            "artifacts",
        ]
        assert [item.type.kind for item in executor.get_output_specs({})] == [
            "string",
            "array",
            "object",
            "array",
            "array",
        ]

    @pytest.mark.anyio
    async def test_non_streaming_forwards_frontend_message_and_attachment_mappings(
        self, context, run, agent_service
    ):
        context.resolve_variable_ref = AsyncMock(
            side_effect={
                "{{start.message}}": "Describe these assets",
                "{{start.attachments}}": [
                    {
                        "url": "https://example.test/image.png",
                        "type": "image_url",
                    },
                    {
                        "url": "https://example.test/report.pdf",
                        "mime_type": "application/pdf",
                    },
                ],
            }.get
        )
        agent = SimpleNamespace(enable_attachments=True, max_iterations=7)
        agent_service.chat = AsyncMock(
            return_value={
                "response": "Done",
                "tool_calls": [],
                "usage": {"total_tokens": 4},
                "dialogue": [{"role": "assistant", "content": "Done"}],
                "artifacts": [{"url": "https://example.test/output.csv"}],
            }
        )
        node = {
            "data": {
                "agentConfig": {
                    "agentId": "agent-1",
                    "messageSource": "variable",
                    "messageVariableRef": "{{start.message}}",
                    "attachmentMappings": [
                        {
                            "name": "attachments",
                            "type": "files",
                            "source": "variable",
                            "variableRef": "{{start.attachments}}",
                        },
                    ],
                    "maxTurns": "5",
                    "stream": False,
                }
            }
        }

        with patch("app.models.agent.Agent.filter") as agent_filter:
            agent_filter.return_value.first = AsyncMock(return_value=agent)
            result = await AgentNodeExecutor().execute(node, context, run)

        assert result.outputs == {
            "response": "Done",
            "toolCalls": [],
            "usage": {"total_tokens": 4},
            "dialogue": [{"role": "assistant", "content": "Done"}],
            "artifacts": [{"url": "https://example.test/output.csv"}],
        }
        agent_service.chat.assert_awaited_once_with(
            agent=agent,
            message="Describe these assets",
            context={},
            images=[{"url": "https://example.test/image.png", "type": "image_url"}],
            files=[
                {
                    "url": "https://example.test/report.pdf",
                    "mime_type": "application/pdf",
                }
            ],
            user_id="user-1",
            max_turns=5,
            user_locale="en",
        )

    @pytest.mark.anyio
    async def test_attachment_mapping_routes_selected_image_variable_without_url_inference(
        self, context, run, agent_service
    ):
        context.resolve_variable_ref = AsyncMock(
            side_effect={"{{start.photo}}": "https://example.test/photo"}.get
        )
        agent = SimpleNamespace(enable_attachments=True, max_iterations=5)
        agent_service.chat = AsyncMock(return_value={})
        node = {
            "data": {
                "agentConfig": {
                    "agentId": "agent-1",
                    "attachmentMappings": [
                        {
                            "name": "attachments",
                            "type": "images",
                            "source": "variable",
                            "variableRef": "{{start.photo}}",
                        },
                    ],
                    "stream": False,
                }
            }
        }

        with patch("app.models.agent.Agent.filter") as agent_filter:
            agent_filter.return_value.first = AsyncMock(return_value=agent)
            await AgentNodeExecutor().execute(node, context, run)

        assert agent_service.chat.await_args.kwargs["images"] == [
            "https://example.test/photo"
        ]
        assert agent_service.chat.await_args.kwargs["files"] is None

    @pytest.mark.anyio
    async def test_rejects_attachments_when_agent_disables_them(
        self, context, run, agent_service
    ):
        context.resolve_variable_ref = AsyncMock(
            side_effect={"{{start.attachments}}": "data:image/png;base64,abc"}.get
        )
        node = {
            "data": {
                "agentConfig": {
                    "agentId": "agent-1",
                    "attachmentMappings": [
                        {
                            "name": "attachments",
                            "type": "files",
                            "source": "variable",
                            "variableRef": "{{start.attachments}}",
                        }
                    ],
                    "stream": False,
                }
            }
        }

        with patch("app.models.agent.Agent.filter") as agent_filter:
            agent_filter.return_value.first = AsyncMock(
                return_value=SimpleNamespace(enable_attachments=False, max_iterations=5)
            )
            result = await AgentNodeExecutor().execute(node, context, run)

        assert result.error == "attachments_not_enabled"
        agent_service.chat.assert_not_called()

    @pytest.mark.anyio
    async def test_streaming_preserves_structured_events_and_artifact_details(
        self, context, run, agent_service
    ):
        agent = SimpleNamespace(enable_attachments=False)

        async def chat_stream(**_kwargs):
            for chunk in (
                "hello",
                {"tool_call": {"id": "call-1"}},
                {
                    "tool_result": {
                        "tool_call_id": "call-1",
                        "result": {
                            "artifacts": [{"name": "artifact"}, "ignored"],
                            "display_result": {"files": [{"name": "nested"}]},
                        },
                    }
                },
                {"usage": {"total_tokens": 2}},
                {"unhandled": True},
                {
                    "dialogue": [{"role": "assistant", "content": "final"}],
                    "artifacts": [{"name": "final"}],
                },
            ):
                yield chunk

        agent_service.chat_stream = chat_stream
        node = {
            "data": {
                "config": {
                    "agentId": "agent-1",
                    "outputVariable": "answer",
                    "stream": True,
                }
            }
        }

        with (
            patch("app.models.agent.Agent.filter") as agent_filter,
            patch(
                "app.services.workflow.executors.tool.StreamManager.publish_token",
                new=AsyncMock(),
            ) as publish_token,
        ):
            agent_filter.return_value.first = AsyncMock(return_value=agent)
            result = await AgentNodeExecutor().execute(node, context, run)

        assert result.outputs == {
            "response": "hello",
            "toolCalls": [{"id": "call-1"}],
            "usage": {"total_tokens": 2},
            "dialogue": [{"role": "assistant", "content": "final"}],
            "artifacts": [{"name": "final"}],
            "answer": "hello",
        }
        publish_token.assert_awaited_once_with("", "hello")

    @pytest.mark.anyio
    async def test_non_streaming_routes_declared_mapping_types_and_locale_fallback(
        self, context, agent_service
    ):
        context.resolve_variable_ref = AsyncMock(
            side_effect={
                "{{start.photos}}": [{"url": "photo"}, None],
                "{{start.document}}": [None, {"url": "document"}],
                "{{start.topic}}": "topic",
                "{{start.selected_photo}}": "selected photo",
                "{{start.more}}": [
                    None,
                    {"type": "image_url", "url": "detected image"},
                    {"url": "plain file"},
                ],
            }.get
        )
        run = MagicMock(triggered_by_id="user-1", triggered_by=None)
        run.fetch_related = AsyncMock()
        agent = SimpleNamespace(enable_attachments=True, max_iterations=4)
        agent_service.chat = AsyncMock(return_value={})
        node = {
            "data": {
                "agentConfig": {
                    "agentId": "agent-1",
                    "messageSource": "constant",
                    "messageConstantValue": "constant prompt",
                    "inputMappings": [
                        {
                            "name": "photos",
                            "type": "images",
                            "source": "variable",
                            "variableRef": "{{start.photos}}",
                        },
                        {
                            "name": "document",
                            "type": "file",
                            "source": "variable",
                            "variableRef": "{{start.document}}",
                        },
                        {
                            "name": "topic",
                            "type": "string",
                            "source": "variable",
                            "variableRef": "{{start.topic}}",
                        },
                        {},
                    ],
                    "attachmentMappings": [
                        {
                            "name": "selected_photo",
                            "attachmentType": "images",
                            "source": "variable",
                            "variableRef": "{{start.selected_photo}}",
                        },
                        {
                            "name": "more",
                            "type": "files",
                            "source": "variable",
                            "variableRef": "{{start.more}}",
                        },
                    ],
                    "stream": False,
                }
            }
        }

        with patch("app.models.agent.Agent.filter") as agent_filter:
            agent_filter.return_value.first = AsyncMock(return_value=agent)
            result = await AgentNodeExecutor().execute(node, context, run)

        assert result.success
        agent_service.chat.assert_awaited_once_with(
            agent=agent,
            message="constant prompt",
            context={"topic": "topic"},
            images=[
                {"url": "photo"},
                "selected photo",
                {"type": "image_url", "url": "detected image"},
            ],
            files=[{"url": "document"}, {"url": "plain file"}],
            user_id="user-1",
            max_turns=4,
            user_locale="en",
        )

    def test_output_metadata_includes_a_distinct_alias(self):
        names = [
            item["name"]
            for item in AgentNodeExecutor().get_output_variables(
                {"outputVariable": "answer"}
            )
        ]

        assert names == [
            "answer",
            "response",
            "toolCalls",
            "usage",
            "dialogue",
            "artifacts",
        ]


class TestHTTPRequestNodeExecutorBehavior:
    @pytest.mark.anyio
    async def test_execute_resolves_request_and_returns_json(self, context, run):
        response = MagicMock(status_code=201, headers={"x-id": "created"})
        response.json.return_value = {"ok": True}
        client = AsyncMock()
        client.request.return_value = response
        client_context = AsyncMock()
        client_context.__aenter__.return_value = client

        node = {
            "data": {
                "config": {
                    "method": "post",
                    "url": "https://example.test/{{start.id}}",
                    "headers": {"Authorization": "Bearer {{start.token}}"},
                    "body": {
                        "message": "{{start.message}}",
                        "nested": {"id": "{{start.id}}"},
                        "items": ["{{start.message}}", {"id": "{{start.id}}"}, 1],
                    },
                    "timeout": 5,
                }
            }
        }

        with patch("httpx.AsyncClient", return_value=client_context) as client_class:
            result = await HTTPRequestNodeExecutor().execute(node, context, run)

        client_class.assert_called_once_with(timeout=5)
        client.request.assert_awaited_once_with(
            method="POST",
            url="https://example.test/42",
            headers={"Authorization": "Bearer secret"},
            json={
                "message": "hello",
                "nested": {"id": "42"},
                "items": ["hello", {"id": "42"}, 1],
            },
            content=None,
        )
        assert result.outputs == {
            "statusCode": 201,
            "body": {"ok": True},
            "headers": {"x-id": "created"},
        }

    @pytest.mark.anyio
    async def test_execute_sends_string_body_and_falls_back_to_text(self, context, run):
        response = MagicMock(status_code=200, headers={})
        response.json.side_effect = json.JSONDecodeError("invalid", "text", 0)
        response.text = "plain response"
        client = AsyncMock()
        client.request.return_value = response
        client_context = AsyncMock()
        client_context.__aenter__.return_value = client

        with patch("httpx.AsyncClient", return_value=client_context):
            result = await HTTPRequestNodeExecutor().execute(
                {
                    "data": {
                        "config": {
                            "url": "https://example.test",
                            "body": "say {{start.message}}",
                        }
                    }
                },
                context,
                run,
            )

        assert client.request.await_args.kwargs["json"] is None
        assert client.request.await_args.kwargs["content"] == "say hello"
        assert result.outputs["body"] == "plain response"

    @pytest.mark.anyio
    async def test_execute_handles_validation_timeout_and_request_errors(
        self, context, run
    ):
        executor = HTTPRequestNodeExecutor()
        missing_url = await executor.execute({"data": {"config": {}}}, context, run)

        client = AsyncMock()
        client.request.side_effect = httpx.TimeoutException("late")
        client_context = AsyncMock()
        client_context.__aenter__.return_value = client

        with (
            patch("httpx.AsyncClient", return_value=client_context),
            patch(
                "app.services.workflow.executors.tool.resolve_user_visible_error",
                side_effect=lambda message, **kwargs: f"public: {message}",
            ),
        ):
            timeout = await executor.execute(
                {"data": {"config": {"url": "https://example.test", "timeout": 2}}},
                context,
                run,
            )
            client.request.side_effect = ValueError("bad request")
            request_error = await executor.execute(
                {"data": {"config": {"url": "https://example.test"}}},
                context,
                run,
            )

        assert missing_url.error == "tool_execution_failed"
        assert timeout.error == "public: Request timed out after 2s"
        assert request_error.error == "public: bad request"

    def test_output_metadata(self):
        executor = HTTPRequestNodeExecutor()

        assert [item["name"] for item in executor.get_output_variables({})] == [
            "statusCode",
            "body",
            "headers",
        ]
        assert [item.type.kind for item in executor.get_output_specs({})] == [
            "number",
            "any",
            "object",
        ]

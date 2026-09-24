"""Tests for the TypeSafe decision adapter, factory, manager routing and admin probe."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest

from app.llm.adapters.decision.factory import create_decision_adapter
from app.llm.adapters.decision.typesafe_adapter import TypeSafeDecisionAdapter
from app.llm.errors import (
    AuthenticationError,
    InsufficientQuotaError,
    InvalidRequestError,
    ProviderError,
    RateLimitError,
)
from app.llm.errors import TimeoutError as LLMTimeoutError
from app.llm.manager import ModelManager
from app.llm.types import DecisionQuestion, DecisionRequest, Usage
from app.models.model import ModelProvider, ModelType

SYSTEMONE_URL = "https://api.typesafe.ai/v1/systemone"


@pytest.fixture(autouse=True)
def allow_model_endpoints(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ModelManager, "_ensure_model_endpoint_allowed", AsyncMock())


def build_config(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "provider": ModelProvider.TYPESAFE,
        "model_id": "jev-latest",
        "api_key": "secret",
        "base_url": None,
        "default_params": None,
        "config": None,
        "max_output_tokens": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def build_request(**overrides: object) -> DecisionRequest:
    values: dict[str, object] = {
        "state": "I was charged twice for the same order.",
        "questions": {
            "refund": DecisionQuestion(
                type="noul", instructions="Does the customer ask for a refund?"
            )
        },
    }
    values.update(overrides)
    return DecisionRequest(**values)


@pytest.mark.parametrize(
    "question",
    [
        {"type": "choice", "criteria": ["yes", "no"]},
        {"type": "choice", "criteria": {"": None}},
        {
            "type": "choice",
            "criteria": {f"option-{index}": None for index in range(256)},
        },
        {"type": "score", "criteria": ["only level"]},
        {"type": "noul", "criteria": ["yes", "no"]},
    ],
)
def test_decision_question_rejects_non_typesafe_criteria(question):
    with pytest.raises(ValueError):
        DecisionQuestion(instructions="Evaluate this state", **question)


def http_status_error(status: int, body: object) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", SYSTEMONE_URL)
    response = httpx.Response(status, json=body, request=request)
    return httpx.HTTPStatusError("boom", request=request, response=response)


def patch_client(response: Mock) -> Mock:
    client = AsyncMock()
    client.post.return_value = response
    context = AsyncMock()
    context.__aenter__.return_value = client
    return patch(
        "app.llm.adapters.decision.typesafe_adapter.httpx.AsyncClient",
        return_value=context,
    )


class TestTypeSafeDecisionAdapter:
    def test_endpoint_requires_base_url_when_provider_is_unknown(self):
        adapter = TypeSafeDecisionAdapter(
            build_config(provider="unknown-provider", base_url=None)
        )

        with pytest.raises(ValueError, match="base_url"):
            adapter._get_endpoint()

    def test_endpoint_uses_configured_then_default_base_url(self):
        configured = TypeSafeDecisionAdapter(
            build_config(base_url="https://proxy.example/v1/")
        )
        assert configured._get_endpoint() == "https://proxy.example/v1/systemone"

        sdk_style = TypeSafeDecisionAdapter(
            build_config(base_url="https://openrouter.ai/api")
        )
        assert sdk_style._get_endpoint() == "https://openrouter.ai/api/v1/systemone"

        defaulted = TypeSafeDecisionAdapter(build_config(base_url=None))
        assert defaulted._get_endpoint() == SYSTEMONE_URL

    def test_headers_and_payload_omit_missing_api_key_and_use_model_config(self):
        adapter = TypeSafeDecisionAdapter(build_config(api_key=None))

        assert adapter._build_headers() == {"Content-Type": "application/json"}
        payload = adapter._build_payload(build_request())
        assert payload["model"] == "jev-latest"
        assert payload["state"] == "I was charged twice for the same order."
        assert payload["questions"] == {
            "refund": {
                "type": "noul",
                "instructions": "Does the customer ask for a refund?",
            }
        }

    def test_headers_and_payload_prefer_explicit_key_and_model(self):
        adapter = TypeSafeDecisionAdapter(
            build_config(provider="typesafe", api_key="key-1")
        )

        assert adapter._build_headers()["Authorization"] == "Bearer key-1"
        payload = adapter._build_payload(build_request(model="jev-1.13.0"))
        assert payload["model"] == "jev-1.13.0"

    def test_payload_preserves_choice_options_and_ordered_score_levels(self):
        adapter = TypeSafeDecisionAdapter(build_config())
        request = DecisionRequest(
            state="Support ticket",
            questions={
                "route": DecisionQuestion(
                    type="choice",
                    instructions="Which team should handle it?",
                    criteria={"support": None, "billing": None},
                ),
                "priority": DecisionQuestion(
                    type="score",
                    instructions="How urgent is it?",
                    criteria=["Not urgent", "Urgent"],
                ),
            },
        )

        assert adapter._build_payload(request)["questions"] == {
            "route": {
                "type": "choice",
                "instructions": "Which team should handle it?",
                "criteria": {"support": None, "billing": None},
            },
            "priority": {
                "type": "score",
                "instructions": "How urgent is it?",
                "criteria": ["Not urgent", "Urgent"],
            },
        }

    def test_provider_value_handles_plain_strings_and_missing_provider(self):
        assert (
            TypeSafeDecisionAdapter(build_config(provider="typesafe"))._provider_value()
            == "typesafe"
        )
        assert (
            TypeSafeDecisionAdapter(build_config(provider=None))._provider_value() == ""
        )

    def test_parse_answers_skips_malformed_entries(self):
        adapter = TypeSafeDecisionAdapter(build_config())

        assert adapter._parse_answers({"answers": "nope"}) == {}
        assert adapter._parse_answers({}) == {}

        answers = adapter._parse_answers(
            {
                "answers": {
                    "refund": {"type": "noul", "noul": 0.82},
                    "scalar": 3,
                    "broken": {"type": "choice", "confidence": "high"},
                }
            }
        )

        assert list(answers) == ["refund"]
        assert answers["refund"].noul == 0.82

    def test_parse_usage_maps_input_and_output_tokens(self):
        adapter = TypeSafeDecisionAdapter(build_config())

        usage = adapter._parse_usage(
            {"usage": {"input_tokens": 296, "output_tokens": 20}}
        )
        assert usage == Usage(
            prompt_tokens=296,
            completion_tokens=20,
            total_tokens=316,
            total_input_tokens=296,
        )

        assert adapter._parse_usage({"usage": None}) == Usage()
        assert adapter._parse_usage({}) == Usage()
        assert adapter._parse_usage({"usage": {"input_tokens": None}}) == Usage()

    def test_decide_posts_systemone_and_returns_typed_answers(self):
        adapter = TypeSafeDecisionAdapter(build_config())
        response = Mock()
        response.json.return_value = {
            "model": "jev-1.13.0",
            "answers": {
                "refund": {
                    "type": "noul",
                    "noul": 0.72,
                }
            },
            "usage": {"input_tokens": 100, "output_tokens": 4},
        }

        with patch_client(response) as client_factory:
            result = asyncio.run(adapter.decide(build_request(), timeout=9))

        client_factory.assert_called_once_with(timeout=9)
        client_factory.return_value.__aenter__.return_value.post.assert_awaited_once_with(
            SYSTEMONE_URL,
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer secret",
            },
            json={
                "state": "I was charged twice for the same order.",
                "model": "jev-latest",
                "questions": {
                    "refund": {
                        "type": "noul",
                        "instructions": "Does the customer ask for a refund?",
                    }
                },
            },
        )
        response.raise_for_status.assert_called_once_with()
        assert result.model == "jev-1.13.0"
        assert result.answers["refund"].noul == 0.72
        assert result.usage.total_tokens == 104

    def test_decide_skips_http_when_no_questions(self):
        adapter = TypeSafeDecisionAdapter(build_config())

        with patch(
            "app.llm.adapters.decision.typesafe_adapter.httpx.AsyncClient"
        ) as client_factory:
            result = asyncio.run(adapter.decide(build_request(questions={})))

        client_factory.assert_not_called()
        assert result.model == "jev-latest"
        assert result.answers == {}

    @pytest.mark.parametrize(
        ("status", "expected"),
        [
            (401, AuthenticationError),
            (402, InsufficientQuotaError),
            (429, RateLimitError),
            (400, InvalidRequestError),
            (422, InvalidRequestError),
            (500, ProviderError),
        ],
    )
    def test_decide_maps_http_status_to_llm_errors(self, status: int, expected: type):
        adapter = TypeSafeDecisionAdapter(build_config())
        response = Mock()
        response.raise_for_status.side_effect = http_status_error(
            status, {"detail": "provider said no"}
        )

        with patch_client(response):
            with pytest.raises(expected) as exc_info:
                asyncio.run(adapter.decide(build_request()))

        assert exc_info.value.message == "provider said no"
        assert exc_info.value.provider == "typesafe"
        assert exc_info.value.model == "jev-latest"
        if status == 500:
            assert exc_info.value.status_code == 500

    def test_decide_maps_transport_failures(self):
        adapter = TypeSafeDecisionAdapter(build_config())

        timeout_response = Mock()
        timeout_response.raise_for_status.side_effect = httpx.ConnectTimeout("slow")
        with patch_client(timeout_response):
            with pytest.raises(LLMTimeoutError) as timeout_exc:
                asyncio.run(adapter.decide(build_request()))
        assert timeout_exc.value.timeout == 60.0

        broken_response = Mock()
        broken_response.raise_for_status.side_effect = httpx.ConnectError("refused")
        with patch_client(broken_response):
            with pytest.raises(ProviderError):
                asyncio.run(adapter.decide(build_request()))

    def test_decide_rejects_non_object_body(self):
        adapter = TypeSafeDecisionAdapter(build_config())
        response = Mock()
        response.json.return_value = ["not", "an", "object"]

        with patch_client(response):
            with pytest.raises(ProviderError, match="unexpected response body"):
                asyncio.run(adapter.decide(build_request()))

    def test_error_message_variants(self):
        adapter = TypeSafeDecisionAdapter(build_config())

        assert (
            adapter._map_http_error(http_status_error(500, {"message": "busy"})).message
            == "busy"
        )
        assert (
            adapter._map_http_error(
                http_status_error(500, {"error": {"code": "overloaded"}})
            ).message
            == "{'code': 'overloaded'}"
        )
        assert (
            adapter._map_http_error(http_status_error(503, {})).message
            == "TypeSafe request failed with status 503"
        )

        plain = httpx.Response(
            502,
            content=b"<html>bad gateway</html>",
            request=httpx.Request("POST", SYSTEMONE_URL),
        )
        error = httpx.HTTPStatusError(
            "bad gateway", request=plain.request, response=plain
        )
        assert (
            adapter._map_http_error(error).message
            == "TypeSafe request failed with status 502"
        )

        listed = httpx.Response(
            500,
            json=[{"detail": "shape changed"}],
            request=httpx.Request("POST", SYSTEMONE_URL),
        )
        listed_error = httpx.HTTPStatusError(
            "server error", request=listed.request, response=listed
        )
        assert (
            adapter._map_http_error(listed_error).message
            == "TypeSafe request failed with status 500"
        )


class TestDecisionFactory:
    def test_factory_returns_typesafe_adapter(self):
        adapter = create_decision_adapter(build_config(provider="typesafe"))

        assert isinstance(adapter, TypeSafeDecisionAdapter)

        from_enum = create_decision_adapter(
            build_config(provider=ModelProvider.TYPESAFE)
        )

        assert isinstance(from_enum, TypeSafeDecisionAdapter)

    def test_factory_rejects_unknown_provider(self):
        with pytest.raises(ValueError, match="Unsupported provider for decision"):
            create_decision_adapter(build_config(provider="openai"))

        with pytest.raises(ValueError, match="Unsupported provider for decision"):
            create_decision_adapter(build_config(provider=None))


class TestModelManagerDecision:
    def test_decide_resolves_decision_model_type(self):
        manager = ModelManager()
        model_uuid = "550e8400-e29b-41d4-a716-446655440000"
        fake_model = SimpleNamespace(
            id=model_uuid,
            name="Jev",
            model_type=ModelType.DECISION,
            is_enabled=True,
        )
        query = SimpleNamespace(first=AsyncMock(return_value=fake_model))
        adapter = SimpleNamespace(decide=AsyncMock(return_value="decided"))

        with (
            patch("app.llm.manager.Model.filter", return_value=query) as mock_filter,
            patch(
                "app.llm.manager.create_decision_adapter", return_value=adapter
            ) as create_adapter,
        ):
            result = asyncio.run(manager.decide(build_request(), model_id=model_uuid))

        assert result == "decided"
        mock_filter.assert_called_once_with(
            id=model_uuid, model_type=ModelType.DECISION
        )
        create_adapter.assert_called_once_with(fake_model)

    def test_decide_accepts_payload_dicts_and_preserves_llm_errors(self):
        manager = ModelManager()
        model_uuid = "550e8400-e29b-41d4-a716-446655440001"
        fake_model = SimpleNamespace(
            id=model_uuid, name="Jev", model_type=ModelType.DECISION, is_enabled=True
        )
        query = SimpleNamespace(first=AsyncMock(return_value=fake_model))
        adapter = SimpleNamespace(
            decide=AsyncMock(side_effect=AuthenticationError(message="bad key"))
        )

        with (
            patch("app.llm.manager.Model.filter", return_value=query),
            patch("app.llm.manager.create_decision_adapter", return_value=adapter),
        ):
            with pytest.raises(AuthenticationError):
                asyncio.run(
                    manager.decide(
                        {
                            "state": "hello",
                            "questions": {
                                "urgent": {
                                    "type": "noul",
                                    "instructions": "Is this urgent?",
                                }
                            },
                        },
                        model_id=model_uuid,
                    )
                )

        sent_request = adapter.decide.await_args.args[0]
        assert isinstance(sent_request, DecisionRequest)
        assert sent_request.state == "hello"

    def test_decide_wraps_unexpected_errors(self):
        manager = ModelManager()
        model_uuid = "550e8400-e29b-41d4-a716-446655440002"
        fake_model = SimpleNamespace(
            id=model_uuid,
            name="Jev",
            model_type=ModelType.DECISION,
            is_enabled=True,
            provider=ModelProvider.TYPESAFE,
            model_id="jev-latest",
        )
        query = SimpleNamespace(first=AsyncMock(return_value=fake_model))
        adapter = SimpleNamespace(
            decide=AsyncMock(side_effect=RuntimeError("rate limit"))
        )

        with (
            patch("app.llm.manager.Model.filter", return_value=query),
            patch("app.llm.manager.create_decision_adapter", return_value=adapter),
        ):
            with pytest.raises(RateLimitError):
                asyncio.run(manager.decide(build_request(), model_id=model_uuid))

    def test_team_decide_records_reported_usage(self):
        manager = ModelManager()
        model_config = SimpleNamespace(
            id="m-1", model_id="jev-latest", provider=ModelProvider.TYPESAFE
        )
        team_model = SimpleNamespace(id="tm-1")
        adapter = SimpleNamespace(
            decide=AsyncMock(
                return_value=SimpleNamespace(
                    answers={},
                    usage=Usage(prompt_tokens=300, total_tokens=320),
                )
            )
        )
        record = AsyncMock()

        with (
            patch.object(
                ModelManager,
                "_get_team_model",
                AsyncMock(return_value=(model_config, team_model)),
            ),
            patch("app.llm.manager.usage_tracker.check_quota_with_model", AsyncMock()),
            patch("app.llm.manager.create_decision_adapter", return_value=adapter),
            patch.object(ModelManager, "_check_and_record_usage", record),
        ):
            result = asyncio.run(manager.team_decide("team-1", build_request()))

        assert result.usage.total_tokens == 320
        record.assert_awaited_once_with(
            team_id="team-1", model_id="m-1", tokens_used=320
        )

    def test_team_decide_estimates_usage_when_provider_reports_none(self):
        manager = ModelManager()
        model_config = SimpleNamespace(
            id="m-1", model_id="jev-latest", provider=ModelProvider.TYPESAFE
        )
        adapter = SimpleNamespace(
            decide=AsyncMock(return_value=SimpleNamespace(answers={}, usage=Usage()))
        )
        record = AsyncMock()

        with (
            patch.object(
                ModelManager,
                "_get_team_model",
                AsyncMock(return_value=(model_config, SimpleNamespace(id="tm-1"))),
            ),
            patch("app.llm.manager.usage_tracker.check_quota_with_model", AsyncMock()),
            patch("app.llm.manager.create_decision_adapter", return_value=adapter),
            patch.object(ModelManager, "_check_and_record_usage", record),
        ):
            asyncio.run(manager.team_decide("team-1", build_request()))

        assert record.await_args.kwargs["tokens_used"] >= 1

    def test_team_decide_accepts_payload_dicts_and_preserves_llm_errors(self):
        manager = ModelManager()
        model_config = SimpleNamespace(
            id="m-1", model_id="jev-latest", provider=ModelProvider.TYPESAFE
        )
        adapter = SimpleNamespace(
            decide=AsyncMock(side_effect=ProviderError(message="provider down"))
        )

        with (
            patch.object(
                ModelManager,
                "_get_team_model",
                AsyncMock(return_value=(model_config, SimpleNamespace(id="tm-1"))),
            ),
            patch("app.llm.manager.usage_tracker.check_quota_with_model", AsyncMock()),
            patch("app.llm.manager.create_decision_adapter", return_value=adapter),
        ):
            with pytest.raises(ProviderError):
                asyncio.run(
                    manager.team_decide(
                        "team-1",
                        {
                            "state": "hello",
                            "questions": {
                                "urgent": {
                                    "type": "noul",
                                    "instructions": "Is this urgent?",
                                }
                            },
                        },
                    )
                )

        assert isinstance(adapter.decide.await_args.args[0], DecisionRequest)

    def test_team_decide_wraps_unexpected_errors(self):
        manager = ModelManager()
        model_config = SimpleNamespace(
            id="m-1",
            model_id="jev-latest",
            provider=ModelProvider.TYPESAFE,
        )
        adapter = SimpleNamespace(
            decide=AsyncMock(side_effect=RuntimeError("rate limit exceeded"))
        )

        with (
            patch.object(
                ModelManager,
                "_get_team_model",
                AsyncMock(return_value=(model_config, SimpleNamespace(id="tm-1"))),
            ),
            patch("app.llm.manager.usage_tracker.check_quota_with_model", AsyncMock()),
            patch("app.llm.manager.create_decision_adapter", return_value=adapter),
        ):
            with pytest.raises(RateLimitError):
                asyncio.run(manager.team_decide("team-1", build_request()))

    def test_team_decide_reports_quota_exceeded(self):
        manager = ModelManager()
        model_config = SimpleNamespace(
            id="m-1", model_id="jev-latest", provider=ModelProvider.TYPESAFE
        )

        from app.services.usage_tracker import QuotaExceededError

        with (
            patch.object(
                ModelManager,
                "_get_team_model",
                AsyncMock(return_value=(model_config, SimpleNamespace(id="tm-1"))),
            ),
            patch(
                "app.llm.manager.usage_tracker.check_quota_with_model",
                AsyncMock(
                    side_effect=QuotaExceededError(
                        "daily token quota exceeded", "daily_tokens"
                    )
                ),
            ),
        ):
            with pytest.raises(Exception) as exc_info:
                asyncio.run(manager.team_decide("team-1", build_request()))

        assert (
            "quota" in str(exc_info.value).lower()
            or exc_info.value.code == "quota_exceeded"
        )


class TestAdminDecisionProbe:
    def test_probe_reports_empty_answers(self):
        from app.api.v1.admin.endpoints.models import _test_decision_model
        from app.schemas.response import BusinessError

        adapter = SimpleNamespace(
            decide=AsyncMock(return_value=SimpleNamespace(answers={}))
        )

        with patch(
            "app.llm.adapters.decision.create_decision_adapter", return_value=adapter
        ):
            with pytest.raises(BusinessError) as exc_info:
                asyncio.run(
                    _test_decision_model(
                        ModelProvider.TYPESAFE,
                        "jev-latest",
                        "key",
                        None,
                        {},
                    )
                )

        assert exc_info.value.msg_key == "model_test_empty_decision_result"

    def test_probe_accepts_non_empty_answers(self):
        from app.api.v1.admin.endpoints.models import _test_decision_model

        adapter = SimpleNamespace(
            decide=AsyncMock(
                return_value=SimpleNamespace(answers={"needs_support": object()})
            )
        )

        with patch(
            "app.llm.adapters.decision.create_decision_adapter", return_value=adapter
        ):
            asyncio.run(
                _test_decision_model(
                    ModelProvider.TYPESAFE, "jev-latest", "key", None, {}
                )
            )

        sent_request = adapter.decide.await_args.args[0]
        assert list(sent_request.questions) == ["needs_support"]

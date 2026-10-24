from uuid import uuid4

import pytest
import pytest_asyncio
from tortoise.context import TortoiseContext

from app.models.observability_payload import ObservabilityToolPayload
from app.services import observability_payload as store


@pytest_asyncio.fixture
async def database():
    async with TortoiseContext() as context:
        await context.init(
            db_url="sqlite://:memory:", modules={"models": ["app.models"]}
        )
        await context.generate_schemas()
        yield


@pytest.mark.asyncio
async def test_records_exact_model_input_and_display_together(database):
    run_id = uuid4()
    await store.record_tool_payload(
        run_id=run_id,
        tool_call_id="call-1",
        tool_name="read_asset",
        display_result='{"filename":"a.pptx","segments":[{"line":1,"text":"x"}]}',
        model_result="a.pptx · lines 1/1\n<document>\n1│x\n</document>",
        renderer="read_asset",
        conversation_id=uuid4(),
    )

    payload = await store.load_tool_payload(run_id=run_id, tool_call_id="call-1")
    assert payload["recorded"] is True
    assert payload["model_input"].startswith("a.pptx")
    assert payload["display"].startswith('{"filename"')
    assert payload["model_bytes"] < payload["display_bytes"]
    assert payload["model_sha256"]
    assert payload["renderer"] == "read_asset"


@pytest.mark.asyncio
async def test_continuation_state_is_visible_without_reading_display(database):
    run_id = uuid4()
    await store.record_tool_payload(
        run_id=run_id,
        tool_call_id="call-2",
        tool_name="read_asset",
        display_result='{"segments":[],"next_cursor":"abc","eof":false}',
        model_result="not finished; cursor=abc",
    )
    meta = await store.payload_metadata(run_id)
    assert meta["call-2"]["eof"] is False
    assert meta["call-2"]["has_cursor"] is True
    assert meta["call-2"]["partial"] is False


@pytest.mark.asyncio
async def test_oversized_payload_is_marked_partial_instead_of_stored(database):
    run_id = uuid4()
    await store.record_tool_payload(
        run_id=run_id,
        tool_call_id="call-3",
        tool_name="bash",
        display_result="x" * (store.MAX_PAYLOAD_BYTES + 1),
        model_result="ok",
    )
    payload = await store.load_tool_payload(run_id=run_id, tool_call_id="call-3")
    assert payload["partial"] is True
    assert payload["display"] is None
    assert payload["model_input"] == "ok"
    assert payload["display_bytes"] > store.MAX_PAYLOAD_BYTES


@pytest.mark.asyncio
async def test_repeated_call_updates_the_same_row(database):
    run_id = uuid4()
    for text in ("first", "second"):
        await store.record_tool_payload(
            run_id=run_id,
            tool_call_id="call-4",
            tool_name="bash",
            display_result=text,
            model_result=text,
        )
    assert await ObservabilityToolPayload.filter(run_id=run_id).count() == 1
    payload = await store.load_tool_payload(run_id=run_id, tool_call_id="call-4")
    assert payload["model_input"] == "second"

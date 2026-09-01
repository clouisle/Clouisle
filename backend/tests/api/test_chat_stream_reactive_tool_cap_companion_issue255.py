"""Superseded by the durable AgentLoop suites.

The tests in this file asserted removed chat.py inline-loop internals
(empty-stream fallback, tool argument parsing, heartbeat/disconnect stop,
reactive tool-call iteration caps, preflight context retry). Those
contracts are owned by AgentLoop and covered by tests/services/test_agent_run_durable.py,
test_agent_run_steering_stop.py, test_agent_loop_behavioral_smoke.py,
tests/services/test_tool_batch_scheduler.py and tests/api/test_agent_loop_parity_characterization.py.
"""

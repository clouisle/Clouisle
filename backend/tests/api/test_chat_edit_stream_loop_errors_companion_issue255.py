"""Superseded by the durable AgentLoop suites.

The tests in this file asserted chat.py's removed inline loop internals
(heartbeat disconnect handling, context retry with compression, error
cleanup matrices, iteration ranges, tool argument parsing, history
override preservation). The AgentLoop worker now owns those contracts;
coverage moved to tests/services/test_agent_run_durable.py,
test_agent_run_steering_stop.py, test_agent_loop_behavioral_smoke.py,
and tests/api/test_agent_loop_parity_characterization.py.
"""

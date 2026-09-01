"""Superseded by the durable AgentLoop suites.

The single test in this file asserted the removed reactive context-length
retry stream (preflight ContextLengthError retry and legacy compression
event injection). Reactive retry was retired; compression is preflight,
loop-owned, and covered by tests/services/test_chat_context_turn_aware_compaction.py
plus tests/api/test_agent_loop_parity_characterization.py.
"""

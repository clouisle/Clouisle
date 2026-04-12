## Feature: Agent chat parity
**Status**: Complete

### Stages
1. **Stage 1**: Extract shared request-building helpers inside `backend/app/api/v1/endpoints/chat.py`
   - **Validation**: Both `/chat` and `/chat/stream` can use the same helper paths for prompt assembly and message building without changing SSE-only behavior.
   - **Status**: Complete
2. **Stage 2**: Align non-stream request semantics with streaming
   - **Validation**: Non-stream supports `file_urls` parsing into `{{fileContent}}`, multimodal `images`, `history_override`, and user-input-request prompting.
   - **Status**: Complete
3. **Stage 3**: Align non-stream tool execution and persisted tool-call shape
   - **Validation**: Non-stream tool execution uses configured timeouts and persisted intermediate `tool_calls` include `display_name`.
   - **Status**: Complete
4. **Stage 4**: Run targeted validation and clean up duplicate logic
   - **Validation**: Targeted backend checks pass and streaming behavior remains unchanged except for shared request-building reuse.
   - **Status**: Complete

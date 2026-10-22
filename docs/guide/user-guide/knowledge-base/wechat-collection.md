# WeChat iLink

Use **personal settings → WeChat iLink** to authorize your account. A connection can remain unused, collect knowledge, or chat with one Agent. **Only one purpose is active at a time.**

1. **Connect** — scan and confirm authorization without selecting a knowledge base or Agent.
2. **Choose a purpose** — select **Do nothing**, **Knowledge collection**, or **Single Agent** and save. Saved configurations are retained when inactive; they do not independently enable a second purpose.

An administrator must first enable **Agent chat**, **Knowledge collection**, or both in **Site Settings → Integrations → WeChat iLink**. Only enabled purposes can be selected; QR authorization is unavailable when both features are off. Existing connections remain visible and backend history is retained. Disabling a platform feature pauses its intake, execution and replies while preserving credentials and pending work; re-enabling resumes eligible work. Already-started operations may finish. Upstream retention determines whether messages sent during a polling pause remain available.

## Connect your account

1. Choose **Authorize with WeChat**, scan the QR code and confirm in WeChat. Enter a verification code if requested.
2. The connection appears with its authorization state. You can leave it unused; configure collection separately before sending content for indexing.

Each verified WeChat identity has at most one platform connection. Different people can configure their own connections to collect into the same knowledge base. A QR code alone does not create a connection, and the platform cannot receive or reply to messages before authorization completes.

## Configure collection (optional)

Choose **Knowledge collection** as the connection's purpose, then select:

- An active knowledge base that you can write to. Read-only shared knowledge bases are not valid targets.
- Optionally a vision model and a speech recognition model authorized for the target team.

Save to activate collection. Choose **None** to stop collecting without disconnecting or deleting the saved target and recognition models. Subsequent messages are ignored, not saved for later processing. Only existing writable knowledge bases can be selected.

Each accepted submission retains its contributor and original target. A purpose change is rejected while accepted work is still pending; wait for it to finish before switching. Changing a target does not migrate existing documents.

## Use an Agent instead

Choose **Single Agent**, select one published Agent that you can use, fill its required input variables, optionally choose a speech recognition model, and save. Knowledge collection becomes inactive; incoming links and files are Agent inputs, not automatic knowledge-base uploads. Returning to **Do nothing** keeps the saved Agent configuration.

Each connection uses its own conversation. Repeated messages continue that conversation; selecting a different Agent isolates its history. Changed starting variables create a new conversation. Conversations remain available in web chat under normal authorization. Personal settings show the current run status and stop control, not an Agent activity list.

Send `/new` (or `/新对话`), `/stop` (`/停止`), `/status` (`/状态`) or `/help` (`/帮助`) to control the conversation. Normal messages are processed in order; they do not start competing runs. When the Agent asks a question, the next answer resumes that waiting run instead of starting another task. `/new` only resets once the current task has finished; otherwise wait or stop it first. Changing the connection's purpose is blocked while work is active; stop it or wait for completion first.

In Agent chat mode, send `/agents` (`/智能体`) to list your accessible published Agents, then `/use <number>` (`/使用 <编号>`) to switch. An accessible Agent's UUID is also accepted. Numbering follows the current name/ID order and can change when Agents are added or renamed. The command updates the same connection configuration as personal settings. It cannot switch while a run, other accepted messages, collection work or replies are pending; finish or stop the work and wait for delivery before trying again. Wait for the successful switch confirmation before sending your next message: already accepted messages are never rerouted. Selecting the current Agent changes nothing. Switching to another Agent uses its default variables and clears the speech recognition model; missing required variables must be configured on the web. Each Agent retains its own conversation when switching back. These commands do not change a knowledge-collection connection into Agent chat; configure Agent chat on the web first.

Agent execution uses the connected user's identity and the application's existing model, tool, knowledge and quota permissions. Revoked access or a disconnected connection prevents further execution or delivery. Before preparing a normal task's attachments or submitting its run, the platform attempts to send a deduplicated “🤔Thinking...” notice (“🤔思考中...” in Chinese); it confirms receipt and preparation, not completion. Messages waiting behind an active run receive the existing busy notice instead. Commands and answers to Agent questions retain their own responses. WeChat receives these status notices, final answers and required interaction prompts, not internal reasoning or tool traces. Notices use the same delivery safeguards: an ambiguous send is not blindly retried, and delivery is not guaranteed when WeChat is unavailable.

| WeChat input | Agent input |
| --- | --- |
| Text | Message text. Commands above are intercepted instead. |
| Image | Image content, using the Agent's vision-capable chat model. |
| File | Conversation-scoped private Asset plus the ordinary file input the web chat uses. |
| Voice | WeChat's own transcript when present; otherwise the downloaded audio is transcribed with the selected speech recognition model. |
| Video | Audio transcript plus sampled frames, when the Agent's models support it. |

Text accompanying an attachment becomes its caption. Attachments beyond the Agent's configured limits, extensions it disallows, and content its models cannot read are rejected with an explicit reply instead of being silently dropped. An audio file received as a generic file is passed to the Agent as that file, exactly like a web-chat upload; it is not auto-transcribed. Voice messages use the transcript path above.

Generated images, videos and files — including generated audio, which is sent as a file rather than a voice message — are uploaded to WeChat as native media. Only text and registered conversation Assets are ever sent; no public storage URL is forwarded. Per-message run and delivery outcomes remain recorded in the backend but are not listed in personal settings. A timeout after transmission is recorded as unconfirmed rather than resent.

## What can be collected?

| Content | Processing |
| --- | --- |
| Plain text | Saved as a Markdown document and indexed automatically. |
| Text containing HTTP/HTTPS links | Each distinct link is fetched; accompanying text is retained as a note. |
| PDF, DOC/DOCX, XLS/XLSX, PPTX, TXT, Markdown, HTML, CSV, JSON | Downloaded and decrypted, then parsed using the existing document pipeline. Text formats require UTF-8. Parser acceptance does not guarantee scanned PDFs have extractable text. |
| Image | Extracted with the selected team-authorized vision model. |
| Voice | Uses a WeChat-provided transcript when available; otherwise transcribes the downloaded audio with the selected speech recognition model. |
| Audio file | Converted and transcribed with the selected speech recognition model. |
| Video | Transcribes an audio stream when present and extracts up to 12 time-labelled frame samples. Frame extraction requires a vision model; an audio stream also requires a speech recognition model. This is not frame-by-frame video understanding. |

Every received attachment is processed independently. Text accompanying attachments is retained as their caption rather than creating another standalone document. Unknown cards and unsupported files, including ZIP archives, produce an explicit failure. Native public-account article cards are not guaranteed to expose an article URL; sending a URL as text uses the supported link path.

Attachments are limited to the smaller of the configured knowledge document upload limit and 100 MiB. Audio/video must have a readable duration of at most 30 minutes. Content that cannot be extracted or indexed is not reported as collected. A website verification page or access restriction may prevent article extraction.

## Results and originals

Collection results are reported through WeChat; inspect the target knowledge base for indexed documents and their processing state. Personal settings do not display submission history or original-download controls. Backend submission records and supported originals are retained, with authenticated record and original-download APIs still subject to contributor and target-access checks. Replayed messages do not create another document; identical extracted content is deduplicated within the target knowledge base while keeping separate submission records.

Only completed indexing is reported as success. WeChat's acceptance of a reply is **not proof that the phone displayed it**. An ambiguous send is not blindly repeated; backend submission records remain the canonical processing result.

## Disconnect

**Disconnect** stops receiving new messages and prevents pending submissions from proceeding. Existing collected documents remain. Reconnecting requires another WeChat authorization. Losing target write access, deletion of the target, or account deactivation stops collection; an expired WeChat authorization is shown in the platform. No unbound-user reminder is sent through WeChat.

## Deployment requirements

Run the API first so its normal schema bootstrap creates the collection and polling tables, then run the ordinary Celery worker deployment and Beat scheduler. While either platform feature is enabled, Beat dispatches bounded polling batches every three seconds to the default queue, which the ordinary worker consumes. Polling is oldest-due first, with bounded concurrency and deployment-wide in-flight slots; under load the actual interval can exceed three seconds instead of creating unlimited tasks.

Ordinary workers need outbound HTTPS access to the official iLink backend, PostgreSQL and Redis. Each polling batch shares a bounded HTTP pool with request-local authentication. Only new Agent or collection receipts wake their business queues; empty/replayed batches do not. An unchanged empty cursor causes no intake write, while changed cursors still commit safely. Existing Agent/collection recovery, encryption and internal upload-gateway behavior are unchanged.

Platform features control which purposes Beat polls and workers process. Fresh installations default to both features off. The first upgrade preserves active authorized personal uses as platform features, without copying personal credentials into the integration record. Subsequent startup does not overwrite administrator selections.

Beat reads saved platform switches directly from the database, normally every two seconds, and removes disabled features' schedules instead of publishing empty tasks. Turning both features off stops all WeChat periodic dispatch after reconciliation; re-enabling restores the relevant schedules without restarting Beat. Already queued tasks still check current feature availability, and already-started operations may finish. A database refresh failure pauses integration schedules but not unrelated maintenance. Restart Beat once when upgrading to load `IntegrationScheduler`; subsequent switch changes need no restart.

Polling parameters remain `WECHAT_POLL_BATCH_SIZE` (64), `WECHAT_POLL_CONCURRENCY` (16) and `WECHAT_POLL_MAX_BATCHES` (8 globally). Polling uses ordinary worker slots, so it competes with other tasks. Keep settings identical across replicas. Batches have a 30-second deadline and a 90-second recoverable claim. See the [upgrade and index instructions](../../operations/upgrading.md#wechat-polling-cutover); defaults are not a production capacity guarantee.

Agent mode also requires a ready Sandbox Worker for sandbox tools and checkpointing existing session workspaces. Keep that service running alongside the normal worker and Beat; removing the WeChat receiver does not remove the sandbox dependency. On macOS, run `backend/.venv/bin/python main.py sandbox-worker --local-dev -c 1` from the repository root to use the Linux container with Bubblewrap. Do not disable isolation to work around a missing `bwrap`. If no sandbox worker is ready, recovery/checkpointing can time out and WeChat reports that the Agent task did not finish; inspect the conversation's AgentRun error and restore the worker before retrying.

> [!IMPORTANT]
> Stop Beat before upgrading. Drain any old dedicated worker's `wechat_poll` backlog before stopping it, or let old claims expire so the new dispatcher can recover them. Start the matching API, ordinary worker and Beat; do not mix old/new polling implementations.

WeChat client availability, account authorization and deployment-network admission are controlled upstream. Validate QR authorization, original article/card delivery, attachment download and actual phone replies using a real account in the production network before announcing availability.

## API

All routes use the current user's JWT under `/api/v1/wechat-knowledge`; they do not accept a platform API key as a substitute for a personal identity.

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/features` | Read the current `agent_chat` and `knowledge_collection` availability; disabled purposes cannot be activated. |
| GET | `/bindings` | List your connections, active `purpose`, saved collection and single-Agent configuration. |
| GET | `/targets` | List active writable knowledge bases. |
| GET | `/models?knowledge_base_id=…` | List enabled team-authorized vision and speech models. |
| POST | `/logins` | Start QR authorization. Takes no body; the connection is not tied to a knowledge base. |
| POST | `/logins/{id}/poll` | Poll your authorization; optionally submit `verify_code`. |
| PUT | `/bindings/{id}/purpose` | Atomically save and activate `none`, `knowledge_collection` or `agent`; only one is active. Collection fields: `knowledge_base_id`, optional `vision_model_id` and `stt_model_id`. Agent fields: `agent_id`, `variables`, optional `stt_model_id`. Active work returns HTTP 409. |
| GET | `/agents` | List your accessible published Agents and their input definitions. |
| GET | `/agent-models?agent_id=…` | List speech recognition models authorized for the Agent's team. |
| GET | `/agent-receipts?binding_id=…` | Read your Agent submissions, run state, conversation link and delivery outcomes. |
| DELETE | `/bindings/{id}` | Disconnect and erase the stored access token. |
| GET | `/receipts?binding_id=…` | Read up to 50 of your most recent submissions. |
| GET | `/items/{id}/original` | Download an original after contributor and target-access checks. |

# Connect WeChat

Use **personal settings → WeChat Connect** to authorize your account. A connection can remain unused, collect knowledge, or chat with one Agent. **Only one purpose is active at a time.**

1. **Connect** — scan and confirm authorization without selecting a knowledge base or Agent.
2. **Choose a purpose** — select **Do nothing**, **Knowledge collection**, or **Single Agent** and save. Saved configurations are retained when inactive; they do not independently enable a second purpose.

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

Each connection uses its own conversation. Repeated messages continue that conversation; selecting a different Agent isolates its history. Changed starting variables create a new conversation. You can view the conversation from the Agent activity records in personal settings, subject to normal authorization.

Send `/new` (or `/新对话`), `/stop` (`/停止`), `/status` (`/状态`) or `/help` (`/帮助`) to control the conversation. Normal messages are processed in order; they do not start competing runs. When the Agent asks a question, the next answer resumes that waiting run instead of starting another task. `/new` only resets once the current task has finished; otherwise wait or stop it first. Changing the connection's purpose is blocked while work is active; stop it or wait for completion first.

Agent execution uses the connected user's identity and the application's existing model, tool, knowledge and quota permissions. Revoked access or a disconnected connection prevents further execution or delivery. Only final answers and required interaction prompts are sent to WeChat, not internal reasoning or tool traces.

| WeChat input | Agent input |
| --- | --- |
| Text | Message text. Commands above are intercepted instead. |
| Image | Image content, using the Agent's vision-capable chat model. |
| File | Conversation-scoped private Asset plus the ordinary file input the web chat uses. |
| Voice | WeChat's own transcript when present; otherwise the downloaded audio is transcribed with the selected speech recognition model. |
| Video | Audio transcript plus sampled frames, when the Agent's models support it. |

Text accompanying an attachment becomes its caption. Attachments beyond the Agent's configured limits, extensions it disallows, and content its models cannot read are rejected with an explicit reply instead of being silently dropped. An audio file received as a generic file is passed to the Agent as that file, exactly like a web-chat upload; it is not auto-transcribed. Voice messages use the transcript path above.

Generated images, videos and files — including generated audio, which is sent as a file rather than a voice message — are uploaded to WeChat as native media. Only text and registered conversation Assets are ever sent; no public storage URL is forwarded. The Agent activity list records each WeChat message's run state and the delivery outcome (`Queued`, `Sending`, `Accepted by WeChat`, `Failed to send`, `WeChat unavailable, not sent`, `Sent, delivery unconfirmed`). A timeout after transmission is recorded as unconfirmed rather than resent.

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

Recent submissions list each item's indexed, duplicate, processing or failed result. Supported originals are retained and can be downloaded from that submission while the contributor still has access to the target. Replayed messages do not create another document; identical extracted content is deduplicated within the target knowledge base while keeping separate submission records.

Only completed indexing is reported as success. WeChat's acceptance of a reply is **not proof that the phone displayed it**. An ambiguous send is not blindly repeated; inspect the canonical submission result in the platform.

## Disconnect

**Disconnect** stops receiving new messages and prevents pending submissions from proceeding. Existing collected documents remain. Reconnecting requires another WeChat authorization. Losing target write access, deletion of the target, or account deactivation stops collection; an expired WeChat authorization is shown in the platform. No unbound-user reminder is sent through WeChat.

## Deployment requirements

Run the API first so its normal schema bootstrap creates the collection tables. Run the existing knowledge Celery worker and Beat scheduler, plus the standalone receiver:

```bash
python main.py wechat-receiver
```

Compose, Helm and the standalone Kubernetes manifest include a `wechat-receiver` deployment. The receiver does not need an uploads volume; knowledge workers use the existing authenticated internal upload gateway in remote-storage mode. The backend image includes `ffmpeg` and `ffprobe`; local knowledge workers need those executables on `PATH` for audio/video extraction. Recognition and embedding models must be configured and authorized for the target team.

The receiver needs outbound HTTPS access to the official iLink backend and WeChat media CDN, plus PostgreSQL and Redis. Collection processing uses the `knowledge` queue; Agent orchestration and runs use the `agent` queue. Beat recovers collection receipts every minute and checks Agent receipts and pending deliveries every three seconds. PostgreSQL locks serialize ownership; credentials, incoming payloads and cursors are encrypted using the deployment's stable `SECRET_KEY`.

> [!IMPORTANT]
> This release moves the collection target and recognition models from the connection row into a separate optional configuration, and drops the old columns. The cutover is **not backward-compatible**: existing API, worker and receiver processes running the previous schema must be stopped before (or together with) the upgrade. Restart the API, the knowledge worker and the receiver as one deployment step; do not leave old application processes running against the upgraded schema.

WeChat client availability, account authorization and deployment-network admission are controlled upstream. Validate QR authorization, original article/card delivery, attachment download and actual phone replies using a real account in the production network before announcing availability.

## API

All routes use the current user's JWT under `/api/v1/wechat-knowledge`; they do not accept a platform API key as a substitute for a personal identity.

| Method | Path | Purpose |
| --- | --- | --- |
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

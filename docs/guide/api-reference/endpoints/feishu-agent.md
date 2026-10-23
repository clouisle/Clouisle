# Feishu Agent Chat API

The Feishu bot callback is a public provider endpoint, authenticated by Feishu's signed event envelope. Do not call it as an application API.

## Callback

`POST /api/v1/integrations/feishu/callback`

Configure this URL in the Feishu Open Platform event subscription settings. The endpoint supports URL verification challenges and encrypted Feishu event callbacks. Configure the event verification token and Encrypt Key in **Site Settings → Integrations → Feishu → Agent chat**; the Encrypt Key must match the key configured in Feishu.

The callback requires `X-Lark-Request-Timestamp`, `X-Lark-Request-Nonce`, and `X-Lark-Signature`. It rejects timestamps more than 300 seconds from server time, verifies the SHA-256 signature before accepting message state, and accepts request bodies up to 64 KiB. For encrypted callbacks, the Encrypt Key is base64-decoded as Feishu's raw 32-byte AES key. URL verification returns the signed challenge only when the verification token matches. The callback endpoint is disabled when `connection_mode` is `long_connection`.

In Feishu Open Platform, enable the **Bot** capability; grant the app `im:message.p2p_msg:readonly` (receive private messages), `im:message:send_as_bot` (send bot replies), `im:resource` (read message attachments and upload generated images/files), and `contact:user.base:readonly` (user identity lookup) scopes; and subscribe to `im.message.receive_v1` (**Receive messages**). Publish the app version and complete any required administrator approval so these permissions take effect. Group-mention receive permissions do not allow private-message intake. Private (`p2p`) text, file, image and rich-text (`post`) messages are accepted; group and bot-sent messages remain ignored.

Callback message intake is authenticated before sender, Agent, or receipt state is read. Replayed provider `message_id` values are deduplicated. Accepted messages bind to a mapped active Clouisle user and that user's selected, authorized published Agent. Without a selection, the bot returns setup/command guidance and creates no AgentRun. Agent runs use Clouisle's durable pipeline and asynchronous idempotent delivery.

Inbound files and rich-text attachments are downloaded through the authenticated message-resource API, stored as private Assets and referenced by the existing durable chat request. The selected Agent must enable attachments; file count, size and extension limits still apply. Download or validation failures produce an explicit reply instead of silently discarding the message. Attachments cannot answer a pending structured question. Startup adds the receipt `attachments` column idempotently; upgrade the API schema before restarting all ordinary workers and their managed receivers. Previously ignored file events have no receipt and are not automatically replayed: send them again after upgrading.

Rich-text file attachments may be carried in the top-level `files` array alongside `content`, rather than as inline `file` tags. Both forms are parsed, and duplicate file keys are included only once. The application also needs `im:message:readonly` when operators inspect original messages using the message-query API; downloading resources uses the message-resource API.

Final assistant responses are delivered as Feishu interactive cards containing a Markdown element. Images (JPEG, PNG, WEBP, GIF, BMP, ICO, TIFF, HEIC; up to 10 MiB) are sent as native image messages, MP4 videos (up to 30 MiB) as native video, and all other files (up to 30 MiB) as file messages. Generated artifacts follow the same authorization rules as WeChat: only Assets from the terminal run's canonical round, scoped to that exact Conversation and Agent team, are delivered. If a legacy canonical message has no round ID, the durable AgentRun's submission round is used to locate tool results. The recipient must still own the Conversation and the Agent must still be authorized when the outbound row is sent; otherwise the artifact is never uploaded. The uploaded `image_key`/`file_key` is stored on the delivery row before replying, so a crash or retry never uploads or attaches a different resource. Upload failures are recorded as delivery errors; only an ambiguous reply timeout becomes `unknown`, and no row is blind-resent.

## Long connection

Set `connection_mode` to `long_connection`, choose long connection event delivery in Feishu Open Platform, and subscribe to `im.message.receive_v1`. Enable the `agent_chat` feature and save app credentials. An existing Celery worker consuming `agent` automatically starts the SDK receiver; no global Agent list or extra service is required.

The SDK authenticates the outbound WebSocket using the saved App ID and App Secret. No public inbound URL or callback secrets are required. Workers elect one receiver using expiring Redis ownership. Feature disable or callback mode stops reception, credential changes replace it, and worker/child failure triggers takeover or restart. Keep the existing API, worker, and Beat running with matching database, Redis and `SECRET_KEY` settings.

The **Connected** state confirms the WebSocket connection, not private-message permissions or event subscription. If no inbound receipts appear, check that `im:message.p2p_msg:readonly` is granted in the published app version and that `im.message.receive_v1` is subscribed with long connection delivery. Send a new private message after the configuration takes effect; previously unreceived messages cannot be assumed to replay.

The receiver rechecks feature selection, ownership, mode and credentials before accepting events. It shares receipt, identity/access and AgentRun paths with callbacks; cross-transport replay does not create another receipt. SDK ACKs follow durable receipt commit; failed commits and credential rotation produce retryable errors. Broker failure leaves a durable receipt for Beat recovery. Outbound delivery runs outside the intake chat lock.

## Administration

The settings APIs are available to administrators with `admin:integrations:settings:read/update`:

- `GET /api/v1/admin/integrations/feishu/agent-chat/config` — return `connection_mode`, capability state, callback-secret configured flags, and `receiver_status: {state, managed}`. States are `disabled`, `callback`, `unconfigured`, `waiting`, `starting`, `connected`, `reconnecting`, and `error`. Status reflects saved configuration. Missing stored mode defaults to `callback`; secret values are never returned.
- `PUT /api/v1/admin/integrations/feishu/agent-chat/config` — optionally select `connection_mode` and set `event_verification_token` / `event_encrypt_key`. Omitted mode and blank/omitted secrets preserve existing values. `agent_ids` is no longer accepted; the administrator candidate endpoint has been removed.

Feature selection is saved through `PUT /api/v1/admin/integrations/{id}` using `enabled_capabilities`, not an integration master switch. App credentials remain under `/api/v1/admin/integrations/feishu/config`; that endpoint does not accept an `is_enabled` toggle. Disabling Agent chat preserves receipts and unsent replies for re-enabling; operations already started may finish.

Beat normally reconciles saved integration switches every two seconds. Turning off `agent_chat` removes `recover-feishu-agent-channel` from its schedule instead of publishing idle recovery tasks; turning it back on restores the ten-second recovery interval without restarting Beat. Already queued recovery tasks recheck the feature before scanning receipts. Feishu Wiki synchronization is separate: its minute dispatcher requires an enabled integration and at least one enabled Wiki source, not `agent_chat`, `directory_sync`, `user_login`, or `notification`. Those capability switches do not pause enabled Wiki sources. Restart Beat once when upgrading to load the feature-aware scheduler.

The secrets are encrypted at rest and write-only. Administrators manage the shared transport; they cannot choose another user's replying Agent through these APIs.

Outbound replies and artifacts are recorded in the shared delivery queue. Inspect their outcomes on the **Delivery log** page (`/deliveries`), documented in the [Delivery Log API](deliveries.md).

## Personal settings

All endpoints require an active authenticated user and operate only on that user. They accept no user ID:

- `GET /api/v1/feishu-agent/config` — `{enabled, is_enabled, linked, agent_id, agent_name, agent_available}`. `enabled` is shared channel availability; `is_enabled` is the user's own switch. Unavailable selected Agent names are not disclosed.
- `GET /api/v1/feishu-agent/agents` — authorized published Agents on live teams as `{id, name, description, team_name}`. Returns an empty list when the channel is unavailable or the user's Feishu identity is not linked.
- `PUT /api/v1/feishu-agent/config` — optional `{agent_id: UUID | null, is_enabled: boolean}`. Omitted fields remain unchanged. A non-null Agent selection requires a linked identity, available channel and normal Agent chat authorization. Turning on also requires a saved authorized Agent. Turning off or clearing is permitted while the channel is paused.

Personal settings and `/use` share one preference per integration/user. Changes affect only later messages, not accepted receipts, running tasks or their conversations. Existing per-Agent chat histories remain isolated. Startup migrates each existing user's latest selected chat session; it does not assign the administrator's old list to all users. Previously unused users must select an Agent. Startup also adds the durable artifact-delivery columns to existing deployments. Deploy matching API and worker versions together and restart workers after the schema cutover.

The personal switch defaults off for new users. Existing users with a saved Agent retain their previous active behavior during the one-time migration; future restarts never overwrite an explicit opt-out. Turning off pauses new intake, pending receipt processing and unsent deliveries without deleting selection, history or pending state. Work already started may finish. Re-enabling resumes pending work. `/use` cannot bypass a disabled personal switch; use personal settings to turn it back on.

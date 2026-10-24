# Notification Design

This group covers notification domain design and external delivery channels.

## Documents

- [Notification spec](NOTIFICATION_SPEC.md)
- [Built-in integration factory direction](#architecture-direction)
- [Deprecated external channel expansion plan](EXTERNAL_NOTIFICATION_CHANNELS.md)

## Architecture Direction

Built-in notification integrations SHOULD use a single integration factory with registered implementations. This is an in-process architecture only; third-party plugin loading, installation, and execution are out of scope.

The factory resolves a stable integration ID to an implementation. Each implementation owns its provider-specific protocol and configuration behavior. The notification domain passes a provider-neutral message and does not branch on SMTP, HTTP, or vendor-specific payloads.

```text
Notification + delivery context
  → integration factory (stable integration ID)
  → integration implementation
      ├─ validate / test connection
      ├─ send notification
      └─ own configuration schema and persistence mapping
```

The common contract SHOULD stay small: integration ID and display metadata, configuration schema/validation, test capability, and notification delivery. Provider-specific operations MUST NOT be forced into every implementation; use optional capability interfaces when a real integration needs additional operations.

The factory SHOULD be a static, explicit registry, not Python dynamic imports or filesystem discovery. Duplicate IDs, missing registrations, and unknown IDs MUST fail closed. Avoid a generic “one protocol fits all” payload; SMTP, generic HTTP Webhook, and future platform APIs retain their own wire formats.

## Migration Plan

1. **Define the contract and registry.** Add a provider-neutral message/context type and typed integration configuration/result types. Register the existing SMTP email and generic Webhook implementations. Keep their current protocols, settings keys, template/signature behavior, error semantics, and test behavior unchanged.
2. **Route sends through the factory.** Replace `AutoNotificationService`'s channel-to-Celery-task mapping and delivery-task protocol calls with factory resolution. Keep Celery as the durable asynchronous boundary and preserve delivery IDs/status/retry behavior. The task payload carries stable integration ID plus notification ID; task names may remain integration-specific where routing compatibility requires it.
3. **Unify integration management APIs.** Introduce factory-backed integration listing, configuration read/write, and test dispatch for built-in integrations. Migrate the current email/Webhook settings UI to use integration IDs and descriptors. Preserve existing API routes during a compatibility period only if deployed clients require them; otherwise update all in-repository callers and remove the old paths in the same cutover.
4. **Migrate persistence and delivery identity.** Keep existing `smtp_*` and `webhook_*` site-setting keys initially. Preserve historical `NotificationDelivery.channel` values and uniqueness semantics; use stable integration IDs for new delivery records only after an explicit model/migration decision. Do not rename enum/database values incidentally during factory adoption.
5. **Prove parity and extension.** Add behavioral tests for registry completeness/unknown IDs, per-integration config validation and test dispatch, message delivery through each implementation, and failure/retry/status transitions. Exercise one deliberately distinct provider protocol through the registry to prove a new integration does not require editing the notification orchestration flow.

## Boundaries and Risks

- This factory manages **notification delivery integrations** only; it is not a general plugin SDK and does not load externally supplied code.
- Keep in-app notifications and audit creation independent from integration availability. A failed external send MUST NOT undo the in-app notification.
- Keep per-integration secrets private and preserve current secret redaction/read-back behavior. Do not return credentials in integration-list responses.
- Integration enablement and channel selection remain separate decisions: selecting an integration for automatic notifications does not override its own enabled/configured state.
- UI forms may differ by integration. Share rendering primitives only where behavior is genuinely common; do not force provider settings into an over-generalized form schema.
- **Not yet decided:** whether delivery records should keep the database `channel` enum or move to a string integration ID. Prefer preserving the current enum until adding more than one new provider demonstrates the need and a migration is specified.
## Scope

Use this area for:
- notification data model and delivery flow
- channel expansion plans
- external messaging provider integration design

"""Constructors for provider-neutral delivery rows in service tests."""


def wechat_delivery_fields(receipt) -> dict:
    """Identity a durable WeChat row copies from its inbound receipt."""
    return {
        "provider_type": "wechat",
        "receipt_id": receipt.id,
        "user_id": receipt.user_id,
        "agent_id": receipt.agent_id,
        "run_id": receipt.run_id,
        "chat_id": str(receipt.binding_id),
        "message_id": receipt.message_id,
    }

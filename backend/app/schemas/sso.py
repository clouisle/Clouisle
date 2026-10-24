from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class UserSSOConnectionSchema(BaseModel):
    """Linked external account, identified by its preserved integration UUID."""

    id: UUID
    integration_id: UUID
    integration_name: str
    integration_display_name: str
    integration_provider_type: str
    integration_icon_url: Optional[str]
    provider_user_id: str
    provider_username: Optional[str]
    provider_email: Optional[str]
    first_login: datetime
    last_login: datetime

    model_config = ConfigDict(from_attributes=True)

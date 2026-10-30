import pytest
from unittest.mock import AsyncMock, patch

from app.services.kb_image_ingestion import IMAGE_DEFAULTS


@pytest.fixture(autouse=True)
def image_settings_defaults():
    """Keep task tests independent of the settings database."""
    with patch(
        "app.services.kb_image_ingestion.image_settings",
        AsyncMock(return_value=IMAGE_DEFAULTS),
    ):
        yield

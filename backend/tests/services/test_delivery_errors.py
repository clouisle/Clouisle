from app.services.delivery_errors import error_detail


def test_error_detail_includes_status_code_code_and_detail():
    class ProviderError(Exception):
        status_code = 429
        code = "rate_limited"
        detail = "slow down"

    detail = error_detail(ProviderError("failed"))
    assert detail == "ProviderError: failed | HTTP 429 | code rate_limited | slow down"


def test_error_detail_omits_missing_attributes_and_bounds_length():
    detail = error_detail(RuntimeError("x" * 3000))
    assert detail.startswith("RuntimeError: xxx")
    assert len(detail) == 2000

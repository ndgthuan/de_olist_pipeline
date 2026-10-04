import pytest

from pipeline.transform import normalize_status


def test_normalize_status_lowercases_and_strips():
    assert normalize_status("  Delivered ") == "delivered"


def test_normalize_status_keeps_clean_value():
    assert normalize_status("shipped") == "shipped"


@pytest.mark.parametrize("raw", ["", "   ", None])
def test_normalize_status_rejects_empty(raw):
    with pytest.raises(ValueError):
        normalize_status(raw)

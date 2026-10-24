from datetime import date

import pytest

from app.cards import CardError, validate

TODAY = date(2026, 10, 17)


def test_accepts_test_card_with_spaces():
    assert validate("4242 4242 4242 4242", 12, 2029, TODAY) == "Visa"


def test_rejects_real_looking_card():
    with pytest.raises(CardError, match="test card"):
        validate("4012888888881881", 12, 2029, TODAY)  # checksum-valid, not allowlisted


def test_rejects_bad_checksum():
    with pytest.raises(CardError, match="isn't valid"):
        validate("4242424242424241", 12, 2029, TODAY)


def test_rejects_expired():
    with pytest.raises(CardError, match="expired"):
        validate("4242424242424242", 9, 2026, TODAY)

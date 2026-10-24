import pytest

from app.bank import BankError, aba_ok, validate


def test_accepts_test_account_with_spaces():
    assert validate("110 000 000", "0001 2345 6789") == "Stripe Test Bank"


def test_rejects_real_looking_routing():
    assert aba_ok("021000021")  # checksum-valid, not allowlisted
    with pytest.raises(BankError, match="test bank"):
        validate("021000021", "000123456789")


def test_rejects_bad_routing_checksum():
    with pytest.raises(BankError, match="routing number isn't valid"):
        validate("110000001", "000123456789")


def test_rejects_unlisted_account():
    with pytest.raises(BankError, match="test bank"):
        validate("110000000", "123456789012")


def test_rejects_short_account():
    with pytest.raises(BankError, match="account number isn't valid"):
        validate("110000000", "123")

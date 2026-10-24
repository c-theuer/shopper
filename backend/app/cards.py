"""DEMO ONLY card handling.

Card details are stored in plain text, which is not PCI compliant. To keep that
safe, only well-known published test card numbers are accepted, so a real card
can never end up in the database.
"""

from datetime import date

TEST_CARDS: dict[str, str] = {
    "4242424242424242": "Visa",
    "4000056655665556": "Visa",
    "4111111111111111": "Visa",
    "5555555555554444": "Mastercard",
    "2223003122003222": "Mastercard",
    "5200828282828210": "Mastercard",
    "378282246310005": "Amex",
    "371449635398431": "Amex",
    "6011111111111117": "Discover",
    "6011000990139424": "Discover",
    "3056930009020004": "Diners Club",
    "3566002020360505": "JCB",
}


class CardError(ValueError):
    pass


def luhn_ok(number: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(number)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def validate(number: str, exp_month: int, exp_year: int, today: date) -> str:
    """Return the card brand, or raise CardError with a user-facing message."""
    digits = "".join(ch for ch in number if ch.isdigit())
    if not 13 <= len(digits) <= 19 or not luhn_ok(digits):
        raise CardError("That card number isn't valid.")
    if digits not in TEST_CARDS:
        raise CardError(
            "This demo only accepts test card numbers, such as 4242 4242 4242 4242. "
            "Never enter a real card here."
        )
    if not 1 <= exp_month <= 12:
        raise CardError("Expiry month must be between 1 and 12.")
    if (exp_year, exp_month) < (today.year, today.month):
        raise CardError("That card has expired.")
    return TEST_CARDS[digits]


def normalize(number: str) -> str:
    return "".join(ch for ch in number if ch.isdigit())

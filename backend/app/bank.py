"""DEMO ONLY bank account linking.

There is no bank partner behind this. To keep it safe, only published test
routing and account numbers are accepted, so a real account can never be linked.
Only the last 4 digits of the account number are stored.
"""

TEST_ROUTING: dict[str, str] = {
    "110000000": "Stripe Test Bank",
}
TEST_ACCOUNTS = {"000123456789", "000111111116"}


class BankError(ValueError):
    pass


def aba_ok(routing: str) -> bool:
    """ABA routing number checksum (weights 3, 7, 1)."""
    if len(routing) != 9 or not routing.isdigit():
        return False
    weights = (3, 7, 1) * 3
    return sum(int(d) * w for d, w in zip(routing, weights)) % 10 == 0


def normalize(number: str) -> str:
    return "".join(ch for ch in number if ch.isdigit())


def validate(routing: str, account: str) -> str:
    """Return the bank name, or raise BankError with a user-facing message."""
    routing, account = normalize(routing), normalize(account)
    if not aba_ok(routing):
        raise BankError("That routing number isn't valid.")
    if not 4 <= len(account) <= 17:
        raise BankError("That account number isn't valid.")
    if routing not in TEST_ROUTING or account not in TEST_ACCOUNTS:
        raise BankError(
            "This demo only accepts test bank numbers, such as routing 110000000 and account 000123456789. "
            "Never enter a real bank account here."
        )
    return TEST_ROUTING[routing]

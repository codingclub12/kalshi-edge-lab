"""Fee math for Kalshi taker fees."""

FEE_RATE = 0.07


def taker_fee(price: float, contracts: float = 1) -> float:
    """Taker fee in dollars: 0.07 x price x (1 - price) x contracts.

    `price` is the per-contract price in dollars (0 to 1). The exchange rounds
    fees up to the next cent on the whole fill; this returns the unrounded
    figure so per-contract math stays smooth.
    """
    if not 0 < price < 1:
        raise ValueError(f"price must be between 0 and 1 exclusive, got {price}")
    if contracts <= 0:
        raise ValueError(f"contracts must be positive, got {contracts}")
    return FEE_RATE * price * (1 - price) * contracts

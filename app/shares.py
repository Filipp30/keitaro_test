"""Share (traffic %) math for offers inside a stream.

Keitaro stores integer shares and does NOT validate that they add up to 100,
so the editor keeps that invariant itself. Integer rounding uses the
largest-remainder method so the total is always exactly 100.
"""

TOTAL = 100


def _largest_remainder(weights: list[float], total: int = TOTAL) -> list[int]:
    if not weights:
        return []
    weight_sum = sum(weights)
    if weight_sum <= 0:
        weights = [1.0] * len(weights)
        weight_sum = float(len(weights))
    exact = [w * total / weight_sum for w in weights]
    floors = [int(x) for x in exact]
    rest = total - sum(floors)
    # Hand out the remaining points to the largest fractional parts;
    # ties go to the earlier offer so the result is deterministic.
    order = sorted(range(len(exact)), key=lambda i: (-(exact[i] - floors[i]), i))
    for i in order[:rest]:
        floors[i] += 1
    return floors


def equal_split(count: int, total: int = TOTAL) -> list[int]:
    """100 split over `count` offers: 3 -> [34, 33, 33]."""
    return _largest_remainder([1.0] * count, total)


def redistribute(shares: list[int], total: int = TOTAL) -> list[int]:
    """Scale existing shares to `total`, keeping their proportions.

    Used after an offer is removed: the freed share is spread over the
    remaining offers in proportion to what they already had.
    """
    return _largest_remainder([float(max(s, 0)) for s in shares], total)


def is_valid(shares: list[int], total: int = TOTAL) -> bool:
    return not shares or (all(0 <= s <= total for s in shares) and sum(shares) == total)

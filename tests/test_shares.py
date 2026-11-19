import pytest

from app.shares import equal_split, is_valid, redistribute


@pytest.mark.parametrize("count,expected", [
    (0, []),
    (1, [100]),
    (2, [50, 50]),
    (3, [34, 33, 33]),
    (6, [17, 17, 17, 17, 16, 16]),
    (7, [15, 15, 14, 14, 14, 14, 14]),
])
def test_equal_split(count, expected):
    assert equal_split(count) == expected
    assert sum(expected) in (0, 100)


@pytest.mark.parametrize("shares,expected", [
    ([50, 25], [67, 33]),          # removed a 25% offer from 50/25/25
    ([34, 33], [51, 49]),          # removed one of 34/33/33
    ([60], [100]),
    ([0, 0], [50, 50]),            # nothing to scale -> equal split
    ([10, 20, 30], [17, 33, 50]),
    ([], []),
])
def test_redistribute_keeps_proportions_and_total(shares, expected):
    result = redistribute(shares)
    assert result == expected
    assert sum(result) in (0, 100)


def test_redistribute_always_sums_to_100():
    for a in range(0, 101, 7):
        for b in range(0, 101 - a, 11):
            assert sum(redistribute([a, b, 3])) == 100


def test_is_valid():
    assert is_valid([])
    assert is_valid([100])
    assert is_valid([50, 50])
    assert not is_valid([60])
    assert not is_valid([110, -10])

import pytest

from kalshi_edge_lab.fees import taker_fee


def test_fee_formula():
    assert taker_fee(0.5, 1) == pytest.approx(0.0175)
    assert taker_fee(0.04, 25) == pytest.approx(0.07 * 0.04 * 0.96 * 25)


@pytest.mark.parametrize("price", [0, 1, -0.1, 1.5])
def test_fee_rejects_bad_price(price):
    with pytest.raises(ValueError):
        taker_fee(price)


def test_fee_rejects_bad_contracts():
    with pytest.raises(ValueError):
        taker_fee(0.5, 0)

from aipro.risk import RiskManager


def test_position_size_respects_minimum_order():
    risk = RiskManager(daily_loss_limit_pct=-10.0)
    assert risk.position_size(10_000, 0.40, 5_000) == 0
    assert risk.position_size(20_000, 0.40, 5_000) == 8_000


def test_daily_loss_latches_halt_and_blocks_new_positions():
    risk = RiskManager(daily_loss_limit_pct=-10.0)
    assert risk.evaluate(-9.9) is False
    assert risk.evaluate(-10.0) is True
    assert risk.evaluate(2.0) is True
    assert risk.position_size(1_000_000, 0.40, 5_000) == 0

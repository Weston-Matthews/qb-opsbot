import pytest

from qb_opsbot.settlement import calc_true_balance, convert_date, parse_settlement, Fees
from sample_statement import GridSheet, build_grid


def test_convert_date():
    assert convert_date(43861.0) == "01/31/2020"
    assert convert_date(44197) == "01/01/2021"


def test_parse_sample_statement(config):
    s = parse_settlement(GridSheet(build_grid()), config["settlement_layout"])
    assert s.contract_number == "C-1001"
    assert s.customer_name == "Acme Salvage Co"          # leading space removed
    assert s.payment_date == "01/31/2020"
    assert s.books_code == "NORTH"

    assert len(s.assay_lots) == 1
    lot = s.assay_lots[0]
    assert lot.control_number == "LC-20-0001"
    assert lot.Pt_vals == [(1.23456, 1100.0)]
    assert lot.Pd_vals == [(0.5, 1000.0), (0.25, 500.0)]  # breakdown rows
    assert lot.Rh_vals == [(0.1, 800.0)]
    assert lot.total == pytest.approx(3400.0)

    assert len(s.non_assay_lots) == 1
    items = s.non_assay_lots[0].items
    assert [i.name for i in items] == ["Widget Core - Large", "Sample Weight - Lot 7", "Oxygen Sensor", "Copper Scrap"]
    assert items[0].rate == pytest.approx(25.0)
    assert s.non_assay_lots[0].total == pytest.approx(650.0)

    assert s.fees.treatment_charge == -150.0
    assert len(s.fees.advances) == 1
    assert s.fees.advances[0].interest == -12.5
    assert s.fees.final_interest == -3.1
    assert s.fees.final_wire == -25.0
    assert s.final_balance == 1834.40
    # The advance is added back to get the full value of the settlement
    assert s.true_final_balance == pytest.approx(3834.40)


def test_layout_is_configurable(config):
    # Same statement shifted one column to the right: only the layout settings change
    grid = [[""] + row for row in build_grid()]
    layout = dict(config["settlement_layout"], value_col=8, books_code_col=2)
    layout["non_assay"] = {"first_row_offset": 2, "name_col": 5, "qty_col": 6, "rate_col": 7}
    s = parse_settlement(GridSheet(grid), layout)
    assert s.contract_number == "C-1001"
    assert s.books_code == "NORTH"
    assert s.final_balance == 1834.40
    assert s.non_assay_lots[0].total == pytest.approx(650.0)
    assert s.assay_lots[0].Pd_vals == [(0.5, 1000.0), (0.25, 500.0)]


def test_calc_true_balance():
    fees = Fees()
    adv = fees.add_advance()
    adv.set_payment(-500.0)
    assert calc_true_balance(fees, 100.0) == 600.0

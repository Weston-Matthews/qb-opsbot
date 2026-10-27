# Runs the settlement module end to end against a mocked QuickBooks session and checks the
# purchase order, invoices and bill it would send. No QuickBooks, Windows or GUI required.
import os
import sys
import types
from unittest import mock

import pytest

from conftest import ROOT
from qb_opsbot import contract, settings


@pytest.fixture
def fake_qb(monkeypatch):
    gui = types.ModuleType("easygui")
    gui.msgbox = gui.exceptionbox = lambda *a, **k: None
    gui.fileopenbox = lambda *a, **k: None
    monkeypatch.setitem(sys.modules, "easygui", gui)

    session = mock.MagicMock()
    response = session.DoRequests.return_value.ResponseList.GetAt.return_value
    response.StatusSeverity = "Info"
    response.Detail.RefNumber.GetValue.return_value = "1042"
    monkeypatch.setattr(contract.qb, "session_manager", lambda: session)
    monkeypatch.setattr(contract.bill_check, "main", lambda *a: 0)          # not already entered
    monkeypatch.setattr(contract.record, "main", lambda *a: 1)              # no tracking workbook
    monkeypatch.setattr(settings, "load_settings", lambda *a: settings.Settings("TEST", False))
    monkeypatch.setattr(contract, "print_invoice", lambda ret: None)
    monkeypatch.setattr(contract, "print_purchase_order", lambda ret: None)

    calls = {"po": [], "invoice": []}
    rqs = []  # request objects seen, in order

    def recorder(kind):
        def add(rq, **kw):
            if rq not in rqs:
                rqs.append(rq)
            calls[kind].append((rqs.index(rq), kw))
        return add

    monkeypatch.setattr(contract, "po_line", recorder("po"))
    monkeypatch.setattr(contract, "invoice_line", recorder("invoice"))
    return session, calls


def test_settlement_becomes_po_invoices_and_bill(config, log_loc, fake_qb, tmp_path):
    session, calls = fake_qb
    statement = os.path.join(ROOT, "samples", "sample_statement.xlsx")
    log = contract.main(statement, log_loc)

    assert "Status: SUCCESS" in log
    assert "Added invoice, purchase order, and bill to QuickBooks" in log

    po_items = [kw.get("item") for _, kw in calls["po"] if kw.get("item")]
    assert po_items[:4] == ["Converters:Assay Pt", "Converters:Assay Pd", "Converters:Assay Pd", "Converters:Assay Rh"]
    descs = [kw.get("desc") for _, kw in calls["po"]]
    assert "Assay- Pt 1.23456 oz Contract # C-1001 01/31/2020" in descs
    assert "Sample Weight - Lot 7" in descs                 # original description kept
    assert "Assay- Interest Charge ADV" in descs and "Assay- Wire Fee FINAL" in descs

    # Two invoices: primary (converter items + sensor override + assay + fees), secondary (scrap metal only)
    # (the mock returns the same request object for both invoices, so split at the secondary invoice's first line)
    lines = [kw for _, kw in calls["invoice"]]
    split = next(i for i, kw in enumerate(lines) if str(kw.get("desc", "")).startswith("PORTION OF"))
    primary, secondary = lines[:split], lines[split:]
    primary_items = [kw.get("item") for kw in primary if kw.get("item")]
    assert "Each:Oxygen Sensor" in primary_items and "Metals:Copper Scrap" not in primary_items
    secondary_items = [kw.get("item") for kw in secondary if kw.get("item")]
    assert secondary_items == ["Metals:Copper Scrap"]
    assert secondary[0]["desc"] == "PORTION OF ACME SALVAGE CO - C-1001"

    # Bill memo names both invoices
    memo_calls = [c for c in session.mock_calls if c[0].endswith("AppendBillAddRq().Memo.SetValue")]
    assert memo_calls[-1][1][0] == "Invoiced Site North #1042, Invoiced Site South #1042"

# Runs the invoice module against a mocked QuickBooks session: one open bill with converter and scrap lines,
# no existing invoices -> two invoices are created and the bill memo is updated once.
import datetime
import sys
import types
from unittest import mock

from qb_opsbot import decon, invoicer


def test_invoices_created_for_uninvoiced_bill(config, log_loc, tmp_path, monkeypatch):
    company = tmp_path / "Site North.qbw"
    company.write_text("")
    gui = types.ModuleType("easygui")
    gui.multenterbox = lambda *a, **k: ["01/01/2020", "01/31/2020"]
    gui.msgbox = gui.exceptionbox = gui.choicebox = lambda *a, **k: None
    monkeypatch.setitem(sys.modules, "easygui", gui)

    session = mock.MagicMock()
    rs = session.DoRequests.return_value.ResponseList.GetAt.return_value
    rs.StatusSeverity = "Info"
    rs.Detail.RefNumber.GetValue.return_value = "2001"
    monkeypatch.setattr(invoicer.qb, "session_manager", lambda: session)

    bill = decon.Bill("TXN-9")
    bill.refNumber = "C-1001"
    bill.txnDate = datetime.date(2020, 1, 31)
    bill.add_item("Converters:Widget Core L", "", 10, 25.0, 250.0)
    bill.add_item("Metals:Copper Scrap", "", 100, 3.0, 300.0)
    bill.amountDue = 550.0
    monkeypatch.setattr(invoicer, "_load_bills", lambda rs: [bill])
    monkeypatch.setattr(invoicer, "_load_invoices", lambda rs: [])

    log = invoicer.main(str(company), log_loc)

    assert "Added Site North invoice #2001" in log
    assert "Added Site South invoice #2001" in log
    assert bill.memo == "Invoiced Site North #2001, Invoiced Site South #2001"
    assert log.count("Changed memo to") == 1      # one BillMod per bill
    session.EndSession.assert_called_once()

import datetime

from qb_opsbot import decon
from qb_opsbot.contract import classify, memo_tag
from qb_opsbot.invoicer import check_date, match_invoices, needs_invoice


def _bill(lines, memo=""):
    bill = decon.Bill("TXN-1")
    bill.refNumber = "C-1001"
    bill.txnDate = datetime.date(2020, 1, 31)
    bill.memo = memo
    for name, total in lines:
        bill.add_item(name, "", 1, total, total)
    bill.amountDue = sum(total for _, total in lines)
    return bill


def test_classify(config):
    inv = config["invoicing"]
    assert classify("Converters:Widget Core L", inv) == "primary"
    assert classify("Each:Oxygen Sensor", inv) == "primary_override"
    assert classify("Metals:Copper Scrap", inv) == "secondary"
    assert classify("Assay Fees:Wire Fee", inv) is None


def test_decon_splits_bill(config):
    inv = config["invoicing"]
    bill = _bill([("Converters:Widget Core L", 250.0), ("Metals:Copper Scrap", 300.0), ("Assay Fees:Wire Fee", -25.0)])
    whole, primary, secondary = decon.main(bill, "North", "South", inv["primary_item_prefixes"], inv["secondary_item_prefixes"])
    assert whole.total == 525.0
    assert primary.total == 250.0 and primary.custName == "North"
    assert secondary.total == 300.0 and secondary.custName == "South"


def test_decon_single_site(config):
    inv = config["invoicing"]
    bill = _bill([("Converters:Widget Core L", 250.0)])
    whole, primary, secondary = decon.main(bill, "North", "South", inv["primary_item_prefixes"], inv["secondary_item_prefixes"])
    assert primary is not None and secondary is None


def test_needs_invoice_reads_memo(config):
    inv = config["invoicing"]
    bill = _bill([("Converters:A", 1.0), ("Metals:B", 2.0)], memo=memo_tag("Site North") + " #10")
    pseudos = decon.main(bill, "N", "S", inv["primary_item_prefixes"], inv["secondary_item_prefixes"])
    assert needs_invoice(bill, pseudos, "Site North", "Site South")
    bill.memo += ", " + memo_tag("Site South") + " #11"
    assert not needs_invoice(bill, pseudos, "Site North", "Site South")


def test_existing_invoice_is_matched_not_duplicated(config):
    inv = config["invoicing"]
    bill = _bill([("Converters:A", 250.0)])
    pseudos = [decon.main(bill, "N", "S", inv["primary_item_prefixes"], inv["secondary_item_prefixes"])]
    existing = decon.Invoice("INV-1")
    existing.refNumber = "1042"
    existing.txnDate = bill.txnDate
    existing.subtotal = 250.01          # within two cents
    todo, todo_pseudos, updated = match_invoices([bill], pseudos, [existing], "Site North", "Site South")
    assert todo == [] and updated == [bill]
    assert bill.memo == "Invoiced Site North #1042"


def test_unmatched_bill_is_queued(config):
    inv = config["invoicing"]
    bill = _bill([("Converters:A", 250.0)])
    pseudos = [decon.main(bill, "N", "S", inv["primary_item_prefixes"], inv["secondary_item_prefixes"])]
    todo, todo_pseudos, updated = match_invoices([bill], pseudos, [], "Site North", "Site South")
    assert todo == [bill] and updated == []


def test_check_date():
    assert check_date("1/31/20") == datetime.datetime(2020, 1, 31)
    assert check_date("01/31/2020") == datetime.datetime(2020, 1, 31)
    assert check_date("13/01/2020") == -1
    assert check_date("2020-01-31") == -1
    assert check_date(None) == -1

# qb-opsbot
# Invoice module
# Written by Weston Matthews (2020)
# Takes a company file and the location of the log, and creates invoices for un-invoiced bills in a date range.
# For each open bill it works out which site invoice(s) the bill implies (see decon.py), looks for existing
# invoices that already match (same date, amount within two cents), creates only the missing ones, and
# updates each bill's memo so the next run skips it. False negatives are preferred over duplicate invoices.

import os
from datetime import datetime

from qb_opsbot import APP_TITLE
from qb_opsbot import connect as qb_connect
from qb_opsbot import decon
from qb_opsbot import logutil
from qb_opsbot import lookup
from qb_opsbot import qb
from qb_opsbot import settings

MODULE = "QuickBooks Invoice Module"
TOLERANCE = 0.02


### HELPER FUNCTIONS ###
def check_date(date):
    # Parses MM/DD/YY or MM/DD/YYYY; returns a datetime, or -1 if the text isn't a valid date
    if type(date) != str or date.count('/') != 2:
        return -1
    month, day, year = date.split('/')
    if len(year) == 2:
        year = "20" + year
    elif len(year) != 4:
        return -1
    try:
        return datetime(int(year), int(month), int(day))
    except ValueError:
        return -1


def within(amount, target, tolerance=TOLERANCE):
    return (amount >= target - tolerance) and (amount <= target + tolerance)


def memo_tag(label):
    return "Invoiced " + label


def _value(field, default):
    return field.GetValue() if field is not None else default


def _load_bills(QueryRs):
    bills = []
    billList = QueryRs.Detail
    for x in range(0, len(billList)):
        billData = billList.GetAt(x)
        bill = decon.Bill(billData.TxnID.GetValue())
        print("Adding bill '" + str(bill.txnID) + "' to list")
        bill.editSeq = billData.EditSequence.GetValue()
        bill.vendorID = billData.VendorRef.ListID.GetValue()
        bill.vendorName = billData.VendorRef.FullName.GetValue()
        bill.refNumber = _value(billData.RefNumber, "None")
        bill.txnDate = billData.TxnDate.GetValue()
        bill.memo = _value(billData.Memo, "")
        bill.isPaid = billData.IsPaid.GetValue()
        bill.amountDue = billData.AmountDue.GetValue()
        bill.openAmount = billData.OpenAmount.GetValue()
        # Linked transactions (the purchase order)
        if billData.LinkedTxnList is not None:
            print("# of Linked Txn List Objects: " + str(len(billData.LinkedTxnList)))
            for y in range(0, len(billData.LinkedTxnList)):
                linked = billData.LinkedTxnList.GetAt(y)
                bill.add_PO(linked.TxnID.GetValue(), linked.TxnDate.GetValue(), _value(linked.RefNumber, "None"),
                            linked.Amount.GetValue(), linked.TxnType.GetAsString(), linked.LinkType.GetAsString())
        else:
            print("No Linked Txn Objects.\n")
        # Expense lines
        if billData.ExpenseLineRetList is not None:
            print("# of Expense Line Items: " + str(len(billData.ExpenseLineRetList)))
            for w in range(0, len(billData.ExpenseLineRetList)):
                expense = billData.ExpenseLineRetList.GetAt(w)
                bill.add_expense(expense.AccountRef.FullName.GetValue(), expense.Amount.GetValue(), _value(expense.Memo, ""))
        else:
            print("No Expenses.\n")
        # Item lines
        if billData.ORItemLineRetList is not None:
            print("# of Line Items: " + str(len(billData.ORItemLineRetList)))
            for z in range(0, len(billData.ORItemLineRetList)):
                item = billData.ORItemLineRetList.GetAt(z).ItemLineRet
                bill.add_item(item.ItemRef.FullName.GetValue(), item.Desc.GetValue(), item.Quantity.GetValue(),
                              item.Cost.GetValue(), item.Amount.GetValue())
        else:
            print("No Line Items.\n")
        bills.append(bill)
    return bills


def _load_invoices(QueryRs):
    invoices = []
    invList = QueryRs.Detail
    for x in range(0, len(invList)):
        invData = invList.GetAt(x)
        invoice = decon.Invoice(invData.TxnID.GetValue())
        print("Adding invoice '" + str(invoice.txnID) + "' to list.")
        invoice.editSeq = invData.EditSequence.GetValue()
        invoice.txnNumber = invData.TxnNumber.GetValue()
        invoice.custID = invData.CustomerRef.ListID.GetValue()
        invoice.custName = invData.CustomerRef.FullName.GetValue()
        invoice.refNumber = _value(invData.RefNumber, "None")
        invoice.txnDate = invData.TxnDate.GetValue()
        invoice.PONumber = _value(invData.PONumber, "None")
        invoice.memo = _value(invData.Memo, "")
        invoice.subtotal = invData.Subtotal.GetValue()
        invoice.balRemain = invData.BalanceRemaining.GetValue()
        if invData.ORInvoiceLineRetList is not None:
            print("# of Line Items: " + str(len(invData.ORInvoiceLineRetList)))
            for z in range(0, len(invData.ORInvoiceLineRetList)):
                item = invData.ORInvoiceLineRetList.GetAt(z).InvoiceLineRet
                if item is not None:
                    name = item.ItemRef.FullName.GetValue() if item.ItemRef is not None else ''
                    rate = item.ORRate.Rate.GetValue() if item.ORRate is not None else None
                    invoice.add_item(name, _value(item.Desc, ''), _value(item.Quantity, None), rate, _value(item.Amount, None))
                else:
                    invoice.add_item('', '', 0, 0, 0)
        else:
            print("No Line Items.\n")
        invoices.append(invoice)
    return invoices


def _query_failed(log_loc, severity, what, message):
    print("Warning logged in log.txt\n")
    word = "a warning" if severity == "Warning" else "an error"
    label = "Warning" if severity == "Warning" else "Error"
    return logutil.entry(log_loc, MODULE, "FAILED", details=[
        "QuickBooks returned " + word + " when requesting " + what,
        label + ": " + str(message)])


def _date_query(sessionManager, kind, start_date, end_date):
    # BillQuery or InvoiceQuery for every transaction dated start_date..end_date, with line items and linked txns
    requestMsgSet = qb.new_request(sessionManager)
    if kind == "bills":
        rq = requestMsgSet.AppendBillQueryRq()
        filt = rq.ORBillQuery.BillFilter
    else:
        rq = requestMsgSet.AppendInvoiceQueryRq()
        filt = rq.ORInvoiceQuery.InvoiceFilter
    print("Requesting " + kind + " query.\n")
    rangeFilter = filt.ORDateRangeFilter.TxnDateRangeFilter.ORTxnDateRangeFilter.TxnDateFilter
    rangeFilter.FromTxnDate.SetValue(start_date)
    rangeFilter.ToTxnDate.SetValue(end_date)
    rq.IncludeLineItems.SetValue(True)
    rq.IncludeLinkedTxns.SetValue(True)
    response = sessionManager.DoRequests(requestMsgSet).ResponseList.GetAt(0)
    qb.print_status(response)
    return response


def needs_invoice(bill, pseudos, primary_label, secondary_label):
    # True unless the memo already shows every invoice the bill implies
    whole, primary, secondary = pseudos
    has_primary = memo_tag(primary_label) in bill.memo
    has_secondary = memo_tag(secondary_label) in bill.memo
    if primary is not None and secondary is not None:
        return not (has_primary and has_secondary)
    if primary is not None:
        return not has_primary
    if secondary is not None:
        return not has_secondary
    return True


def match_invoices(bills, pseudos, invoices, primary_label, secondary_label):
    # Compares every bill's pseudo-invoices to the real invoices. Returns
    # (to_be_invoiced, to_be_inv_pseudos, to_be_updated): bills that still need invoices (with the pseudos
    # left to create) and bills whose memo should be updated because a matching invoice already exists.
    to_be_invoiced = []
    to_be_inv_pseudos = []
    to_be_updated = []
    p_tag = memo_tag(primary_label)
    s_tag = memo_tag(secondary_label)
    for bill, bill_pseudos in zip(bills, pseudos):
        print("Checking bill #" + str(bill.refNumber))
        whole, primary, secondary = bill_pseudos
        bill_added = False
        for invoice in invoices:
            if invoice.txnDate != bill.txnDate:
                continue
            # Dates match, check amount within 2 cents for each pseudo
            if within(invoice.subtotal, whole.total):
                # One invoice covers the whole bill
                bill.memo += p_tag + " #" + str(invoice.refNumber)
                to_be_updated.append(bill)
                bill_added = True
                break
            elif primary is not None:
                if within(invoice.subtotal, primary.total):
                    # It matches the primary pseudo; drop it so we don't duplicate it later
                    bill_pseudos = (bill_pseudos[0], None, bill_pseudos[2])
                    if p_tag not in bill.memo:
                        bill.memo = p_tag + " #" + str(invoice.refNumber)
                        to_be_updated.append(bill)
                        bill_added = True
                    if secondary is not None:
                        # A secondary invoice is needed too; see if it already exists
                        for invoice_n in invoices:
                            if invoice_n.txnDate == bill.txnDate and within(invoice_n.subtotal, secondary.total):
                                if s_tag not in bill.memo:
                                    if p_tag in bill.memo:
                                        bill.memo += ", " + s_tag + " #" + str(invoice_n.refNumber)
                                    else:
                                        bill.memo = s_tag + " #" + str(invoice_n.refNumber)
                                    if not bill_added:
                                        to_be_updated.append(bill)
                                        bill_added = True
                                bill_pseudos = (bill_pseudos[0], bill_pseudos[1], None)
                                break
            elif secondary is not None:
                if within(invoice.subtotal, secondary.total):
                    # It matches the secondary pseudo
                    if s_tag not in bill.memo:
                        if p_tag in bill.memo:
                            bill.memo += ", " + s_tag + " #" + str(invoice.refNumber)
                        else:
                            bill.memo = s_tag + " #" + str(invoice.refNumber)
                        if not bill_added:
                            to_be_updated.append(bill)
                            bill_added = True
                    bill_pseudos = (bill_pseudos[0], bill_pseudos[1], None)
            if bill_added:
                break
        if not bill_added:
            # No corresponding invoice, so this bill goes on the to-be-invoiced list
            print("No invoices matched, adding bill to invoiceables list")
            to_be_invoiced.append(bill)
            to_be_inv_pseudos.append(bill_pseudos)
    return to_be_invoiced, to_be_inv_pseudos, to_be_updated


def _update_memos(sessionManager, bills, log):
    print("Updating bill memos...")
    for bill in bills:
        requestMsgSet = qb.new_request(sessionManager)
        billModRq = requestMsgSet.AppendBillModRq()
        billModRq.TxnID.SetValue(bill.txnID)
        billModRq.EditSequence.SetValue(bill.editSeq)
        billModRq.Memo.SetValue(bill.memo)
        rs = sessionManager.DoRequests(requestMsgSet).ResponseList.GetAt(0)
        print("Response code: " + str(rs.StatusSeverity) + "\n")
        status = {"Info": "SUCCESS", "Warning": "WARNING", "Error": "ERROR"}.get(rs.StatusSeverity, str(rs.StatusSeverity))
        log.write("Bill #" + str(bill.refNumber) + " | " + status + " | Changed memo to '" + str(bill.memo) + "'\n")
        if rs.StatusSeverity != "Info":
            log.write("    Message:" + str(rs.StatusMessage) + "\n")
    print("Done updating bills!\n")


def _create_invoice(sessionManager, bill, pseudo, customer, site_label, generated_by, log):
    # Sends one InvoiceAdd for a pseudo-invoice; returns the new invoice's RefNumber, or None
    requestMsgSet = qb.new_request(sessionManager)
    invoiceAddRq = requestMsgSet.AppendInvoiceAddRq()
    invoiceAddRq.CustomerRef.FullName.SetValue(customer)
    invoiceAddRq.TxnDate.SetValue(bill.txnDate)
    invoiceAddRq.Memo.SetValue("Generated by " + generated_by + ", Bill #" + str(bill.refNumber))
    for lineItem in pseudo.lineItems:
        line = invoiceAddRq.ORInvoiceLineAddList.Append().invoiceLineAdd
        line.ItemRef.FullName.SetValue(lineItem.name)
        line.Desc.SetValue(lineItem.desc)
        line.Quantity.SetValue(lineItem.pcs)
        line.Amount.SetValue(lineItem.total)
    rs = sessionManager.DoRequests(requestMsgSet).ResponseList.GetAt(0)
    print("Response code: " + str(rs.StatusSeverity) + "\n")
    if rs.StatusSeverity == "Info":
        ref = str(rs.Detail.RefNumber.GetValue())
        log.write("Bill #" + str(bill.refNumber) + " | SUCCESS | Added " + site_label + " invoice #" + ref + "\n")
        return ref
    if rs.StatusSeverity == "Warning":
        ref = str(rs.Detail.RefNumber.GetValue())
        log.write("Bill #" + str(bill.refNumber) + " | WARNING | Added " + site_label + " invoice #" + ref + "\n")
    else:
        log.write("Bill #" + str(bill.refNumber) + " | ERROR | Failed to add " + site_label + " invoice\n")
    log.write("    Message:" + str(rs.StatusMessage) + "\n")
    return None


def main(path, log_loc):
    import easygui as gui
    config = settings.load_config()
    invoicing = config["invoicing"]
    primary_label = invoicing["primary"]["label"]
    secondary_label = invoicing["secondary"]["label"]
    title = APP_TITLE

    ### Check the file path to make sure it exists and is a QB company file
    if not os.path.exists(path) or path[-4:] not in ['.qbw', '.QBW']:
        print("Selected file is not a QuickBooks company file! Returning to menu...\n")
        return ""
    print("Company file path confirmed!\n")
    books_code = lookup.main(path)
    if books_code == 0:
        # User failed to select a valid company file or books code
        return 0
    # Grab the customer FullNames for the two sites
    custNames = lookup.item([invoicing["primary"]["customer_key"], invoicing["secondary"]["customer_key"]], books_code, log_loc)
    if isinstance(custNames, tuple):
        return custNames[1]
    cust_primary, cust_secondary = custNames[0], custNames[1]

    ### Prompt the user for a date range (start date & end date)
    msg = "Enter the date range of the bills to review.\n(Must be in the form MM/DD/YY or MM/DD/YYYY)"
    fieldValues = gui.multenterbox(msg, title, ["Start Date", "End Date"])
    if fieldValues is None:
        return 0
    start_date = check_date(fieldValues[0])
    end_date = check_date(fieldValues[1])
    if start_date == -1 or end_date == -1:
        print("Error logged in log.txt\n")
        return logutil.entry(log_loc, MODULE, "FAILED", details=[
            "Error: Incorrect date range entered", "Date range entered:",
            "Start Date: " + str(fieldValues[0]), "End Date: " + str(fieldValues[1])])

    ### Open the company file and pull all bills and invoices in the date range
    sessionManager = qb.session_manager()
    print("QuickBooks opened.\n")
    sessionManager.OpenConnection(*qb.APP_INVOICE)
    print("Connection opened.\n")
    try:
        sessionManager.BeginSession(path, qb.OM_DONT_CARE)
        print("Session started.\n")
    except Exception:  # COM errors from QBFC
        gui.exceptionbox(title=title)
        return 0

    try:
        QueryRs = _date_query(sessionManager, "bills", start_date, end_date)
        if QueryRs.StatusSeverity != "Info":
            return _query_failed(log_loc, QueryRs.StatusSeverity, "bills", QueryRs.StatusMessage)
        bills = _load_bills(QueryRs)
        if len(bills) == 0:
            print("No bills found! Returning to main menu...\n")
            gui.msgbox("No bills were found in the date range provided!", title)
            return 0
        print("Done adding " + str(len(bills)) + " bills to list!")

        QueryRs = _date_query(sessionManager, "invoices", start_date, end_date)
        if QueryRs.StatusSeverity != "Info":
            return _query_failed(log_loc, QueryRs.StatusSeverity, "invoices", QueryRs.StatusMessage)
        invoices = _load_invoices(QueryRs)
        print("Done adding " + str(len(invoices)) + " invoice(s) to memory!")

        ### Discard bills which are paid, have no line items, or are already fully invoiced
        print("Examining bills...")
        kept = [bill for bill in bills
                if not bill.isPaid and len(bill.lineItems) > 0
                and not (memo_tag(primary_label) in bill.memo and memo_tag(secondary_label) in bill.memo)]
        print("Discarded " + str(len(bills) - len(kept)) + " bills from list.\n")
        bills = kept
        if len(bills) == 0:
            gui.msgbox("There are no bills in the date range to invoice!", title)
            return 0

        ### Build the pseudo-invoices each bill implies: (whole, primary, secondary)
        pseudos = [decon.main(bill, cust_primary, cust_secondary,
                              invoicing["primary_item_prefixes"], invoicing["secondary_item_prefixes"]) for bill in bills]
        print("Pseudo-invoices: " + str(pseudos) + "\n")

        # Second pass: keep only bills whose memo doesn't already show every invoice they need
        print("Examining bills, second pass...")
        keep = [needs_invoice(bill, p, primary_label, secondary_label) for bill, p in zip(bills, pseudos)]
        print(str(keep.count(False)) + " bills discarded!\n")
        bills = [bill for bill, k in zip(bills, keep) if k]
        pseudos = [p for p, k in zip(pseudos, keep) if k]
        if len(bills) == 0:
            gui.msgbox("There are no bills to invoice in the date range!", title)
            return 0

        print("Comparing invoices to pseudo-invoices...\n")
        to_be_invoiced, to_be_inv_pseudos, to_be_updated = match_invoices(bills, pseudos, invoices, primary_label, secondary_label)

        log = logutil.RunLog(log_loc)
        if len(to_be_invoiced) == 0:
            if len(to_be_updated) == 0:
                print("No bills to invoice or update!\n")
                return "No bills to invoice or update!"
            log.write(MODULE + "\n" + "Timestamp: " + logutil.timestamp() + "\n" + "Status of updated bills:\n")
            _update_memos(sessionManager, to_be_updated, log)
            return log.text

        # Create the missing invoices, then update the memo of every bill that changed
        print("Bills to be invoiced:")
        for bill in to_be_invoiced:
            print(str(bill))
        log.write(MODULE + "\n" + "Timestamp: " + logutil.timestamp() + "\n" + "Status of invoiced bills:\n")
        generated_by = invoicing["generated_by"]
        for bill, (whole, primary, secondary) in zip(to_be_invoiced, to_be_inv_pseudos):
            print("Invoicing bill #" + str(bill.refNumber))
            if primary is not None:
                ref = _create_invoice(sessionManager, bill, primary, cust_primary, primary_label, generated_by, log)
                if ref is not None:
                    bill.memo = memo_tag(primary_label) + " #" + ref
                    to_be_updated.append(bill)
            if secondary is not None:
                ref = _create_invoice(sessionManager, bill, secondary, cust_secondary, secondary_label, generated_by, log)
                if ref is not None:
                    if memo_tag(primary_label) in bill.memo:
                        bill.memo += ", " + memo_tag(secondary_label) + " #" + ref
                    else:
                        bill.memo = memo_tag(secondary_label) + " #" + ref
                    if bill not in to_be_updated:
                        to_be_updated.append(bill)
        log.write("Status of updated bills:\n")
        _update_memos(sessionManager, to_be_updated, log)
        return log.text
    finally:
        qb.close(sessionManager)


def connect(file, log_loc):
    # Registers this module's AppID with the company file
    return qb_connect.authorize(file, log_loc, qb.APP_INVOICE, MODULE)


if __name__ == "__main__":
    print("Not available outside of the bot framework.")

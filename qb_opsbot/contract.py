# qb-opsbot
# Settlement module
# Written by Weston Matthews (2020)
# Reads a refiner's settlement statement (Excel) and enters it into QuickBooks as:
#   1. a purchase order to the vendor,
#   2. one or two invoices to the receiving site(s), depending on which items the settlement contains,
#   3. a bill linked to the purchase order, with a memo naming the invoices that were created.
# Before anything is written, the settlement is screened (vendor and every item must map to QuickBooks names)
# and checked against existing bills so the same settlement is never entered twice.

from datetime import datetime

from qb_opsbot import APP_TITLE
from qb_opsbot import bill_check
from qb_opsbot import connect as qb_connect
from qb_opsbot import logutil
from qb_opsbot import lookup
from qb_opsbot import qb
from qb_opsbot import record
from qb_opsbot import screening
from qb_opsbot import settings
from qb_opsbot.settlement import parse_settlement

MODULE = "QuickBooks Settlement Module"


### HELPER FUNCTIONS ###
def money(value):
    return float(format(value, '.2f'))


def _has_any(text, fragments):
    return any(fragment in text for fragment in fragments)


def classify(item_code, invoicing):
    # Decides which invoice a QuickBooks item belongs on:
    #   "primary"          - primary site's invoice, keeps the item description
    #   "primary_override" - secondary-type item that still goes on the primary invoice (no description)
    #   "secondary"        - secondary site's invoice
    #   None               - not invoiced
    if _has_any(item_code, invoicing["primary_item_prefixes"]):
        return "primary"
    if _has_any(item_code, invoicing["secondary_item_prefixes"]):
        if _has_any(item_code, invoicing["primary_override_keywords"]):
            return "primary_override"
        return "secondary"
    return None


def memo_tag(label):
    # Text the bill memo carries once a site's invoice exists, e.g. "Invoiced Site North #1042"
    return "Invoiced " + label


def get_company_file(code, config=None):
    # Returns the QB company file configured for a books code, or asks the user to pick one
    config = config or settings.load_config()
    code = settings.resolve_books_code(code, config)
    book = config["books"].get(code)
    if book and book.get("company_file"):
        return book["company_file"]
    import easygui
    msg = "Company file not found in list. Please select QuickBooks company file to use."
    print(msg)
    easygui.msgbox(msg, title=APP_TITLE, ok_button='OK')
    return easygui.fileopenbox()


def po_line(rq, item=None, desc=None, qty=None, rate=None, amount=None):
    line = rq.ORPurchaseOrderLineAddList.Append().PurchaseOrderLineAdd
    if item is not None:
        line.ItemRef.FullName.SetValue(item)
    if desc is not None:
        line.Desc.SetValue(desc)
    if qty is not None:
        line.Quantity.SetValue(qty)
    if rate is not None:
        line.Rate.SetValue(rate)
    if amount is not None:
        line.Amount.SetValue(amount)


def invoice_line(rq, item=None, desc=None, qty=None, rate=None, amount=None):
    line = rq.ORInvoiceLineAddList.Append().invoiceLineAdd
    if item is not None:
        line.ItemRef.FullName.SetValue(item)
    if desc is not None:
        line.Desc.SetValue(desc)
    if qty is not None:
        line.Quantity.SetValue(qty)
    if rate is not None:
        line.ORRatePriceLevel.Rate.SetValue(rate)
    if amount is not None:
        line.Amount.SetValue(amount)


def add_assay_lines(add_line, s, metal_items, prefix):
    # One line per metal value; a control-number heading when there is more than one lot; a blank line after each lot
    for lot in s.assay_lots:
        if len(s.assay_lots) > 1:
            add_line(desc=lot.control_number)
        for symbol in ("Pt", "Pd", "Rh"):
            for qty, amount in lot.values(symbol):
                add_line(item=metal_items[symbol],
                         desc=prefix + " " + symbol + " " + str(qty) + " oz Contract # " + str(s.contract_number) + " " + s.payment_date,
                         qty=qty, amount=money(amount))
        add_line(desc=" ")


def add_fee_lines(add_line, fees, fee_items, prefix):
    # Treatment charge first, then every advance's interest and wire fee, then the final interest and wire fee
    add_line(item=fee_items["treatment"], desc=prefix + " Treatment Charge", amount=money(fees.treatment_charge))
    for adv in fees.advances:
        if adv.interest != 0.00:
            add_line(item=fee_items["interest"], desc=prefix + " Interest Charge ADV", amount=money(adv.interest))
        if adv.wire != 0.00:
            add_line(item=fee_items["wire"], desc=prefix + " Wire Fee ADV", amount=money(adv.wire))
    if fees.final_interest != 0.00:
        add_line(item=fee_items["interest"], desc=prefix + " Interest Charge FINAL", amount=money(fees.final_interest))
    if fees.final_wire != 0.00:
        add_line(item=fee_items["wire"], desc=prefix + " Wire Fee FINAL", amount=money(fees.final_wire))


def print_line_items(ret_list, attr):
    # Prints every line of a PurchaseOrderAdd / InvoiceAdd response: ListID | FullName | Desc | Quantity | Amount
    print("--Line Items-------------")
    for x in range(0, len(ret_list)):
        line = getattr(ret_list.GetAt(x), attr)
        if (line.ItemRef is not None) and (line.Quantity is not None):
            print(str(line.ItemRef.ListID.GetValue()) + " | " + str(line.ItemRef.FullName.GetValue()) + " | " + str(line.Desc.GetValue())
                  + " | " + str(line.Quantity.GetValue()) + " units" + " | " + "$" + str(line.Amount.GetValue()))
        elif (line.ItemRef is None) and (line.Desc is not None):
            print(line.Desc.GetValue())
        elif (line.ItemRef is not None) and (line.Quantity is None):
            print(str(line.ItemRef.ListID.GetValue()) + " | " + str(line.ItemRef.FullName.GetValue()) + " | " + str(line.Desc.GetValue())
                  + " | " + "$" + str(line.Amount.GetValue()))
        else:
            print("")
    print("")


def print_invoice(ret):
    print("Customer FullName: " + str(ret.CustomerRef.FullName.GetValue()))
    print("Customer ListID: " + str(ret.CustomerRef.ListID.GetValue()))
    print("Taxation Date: " + str(ret.TxnDate.GetValue()))
    print("Reference Number: " + str(ret.RefNumber.GetValue()))
    print("PO Number: " + str(ret.PONumber.GetValue()))
    print_line_items(ret.ORInvoiceLineRetList, "InvoiceLineRet")
    print("Subtotal: $" + str(ret.Subtotal.GetValue()))
    print("\n")


def print_purchase_order(ret):
    print("Vendor FullName: " + str(ret.VendorRef.FullName.GetValue()))
    print("Vendor ListID: " + str(ret.VendorRef.ListID.GetValue()))
    print("Taxation Date: " + str(ret.TxnDate.GetValue()))
    print("PO Number: " + str(ret.RefNumber.GetValue()))
    print_line_items(ret.ORPurchaseOrderLineRetList, "PurchaseOrderLineRet")
    print("Total Amount: $" + str(ret.TotalAmount.GetValue()))
    print("\n")


def handle_response(response_set, request_name, contract_number, log_loc, printer=None):
    # Prints and logs one QBFC response. Returns (succeeded, log_text).
    rs = response_set.ResponseList.GetAt(0)
    print("Printing " + request_name + " response information:\n")
    qb.print_status(rs)
    severity = rs.StatusSeverity
    if severity == "Info":
        if printer is not None:
            printer(rs.Detail)
        return True, ""
    action = "Attempting to request " + request_name + " from QuickBooks API"
    details = logutil.status_details(rs.StatusCode, severity, rs.StatusMessage)
    if severity == "Warning":
        # Problems have arisen: print what QuickBooks actually recorded so it can be compared with what was sent
        if printer is not None:
            print("You may want to check the transaction to see what went wrong.")
            print("Information added according to QuickBooks:\n")
            printer(rs.Detail)
        print("Warning logged in log.txt\n")
        return False, logutil.entry(log_loc, "Contract # " + str(contract_number), "WARNING", action, details)
    print("Error logged in log.txt\n")
    return False, logutil.entry(log_loc, "Contract # " + str(contract_number), "FAILED", action, details)


# main() takes the file path of the settlement spreadsheet and the file path of the log
# Returns a log of what happened as a string
def main(file, log_loc):
    import easygui
    import xlrd
    config = settings.load_config()
    layout = config["settlement_layout"]
    items_cfg = config["items"]
    invoicing = config["invoicing"]
    prefix = items_cfg["line_desc_prefix"]

    # Open Excel workbook and select the statement page
    try:
        wb = xlrd.open_workbook(file)
        print("Workbook opened.\n")
        sheet = wb.sheet_by_index(layout["sheet_index"])
        print("Sheet " + str(layout["sheet_index"]) + " opened.\n")
    except (OSError, IndexError, ValueError, xlrd.XLRDError):
        easygui.exceptionbox(title=APP_TITLE)
        print("Error logged in log.txt\n")
        return logutil.entry(log_loc, MODULE, "FAILED", "Attempting to open Excel spreadsheet",
                             ["Settlement spreadsheet file path: " + str(file)])

    ### Read the statement into memory ###
    s = parse_settlement(sheet, layout)
    print(s)
    print("Reading Complete!\n")
    contract_number = str(s.contract_number)

    ### Screening the settlement to make sure it can be entered ###
    print("Screening settlement...")
    scrn_rslt = screening.main(s.customer_name, s.item_names(), s.books_code, log_loc)
    if scrn_rslt != 0:
        print("Settlement did not pass screening! Error logged in log.txt\n")
        return scrn_rslt[1]

    # Construct the datetime object to be used with the invoice/PO
    inv_date = datetime.strptime(s.payment_date, "%m/%d/%Y")

    # Find the company file (debug mode always asks)
    if not settings.load_settings(config).debug:
        comp = get_company_file(s.books_code, config)
    else:
        easygui.msgbox("Please select the QuickBooks company file to use.", title=APP_TITLE, ok_button='OK')
        comp = easygui.fileopenbox()

    ### Make sure the settlement has not been entered already ###
    bill_rslt = bill_check.main(comp, s.customer_name, inv_date, s.true_final_balance, log_loc)
    if bill_rslt != 0:
        if bill_rslt[0] == 1:
            print("Settlement has already been input. Bill information logged in log.txt\n")
        else:
            print("Settlement did not pass screening! Error logged in log.txt\n")
        return bill_rslt[1]
    print("Settlement passed screening! Continuing...\n")

    ### Look up every QuickBooks name before opening the session ###
    ven_name = lookup.vendor(s.customer_name, log_loc)
    if not isinstance(ven_name, str):
        return ven_name[1]
    metal_keys = items_cfg["assay_metals"]
    names = lookup.item([metal_keys["Pt"], metal_keys["Pd"], metal_keys["Rh"]], s.books_code, log_loc)
    if isinstance(names, tuple):
        return names[1]
    metal_items = {"Pt": names[0], "Pd": names[1], "Rh": names[2]}
    fee_keys = items_cfg["fees"]
    names = lookup.item([fee_keys["treatment"], fee_keys["interest"], fee_keys["wire"]], s.books_code, log_loc)
    if isinstance(names, tuple):
        return names[1]
    fee_items = {"treatment": names[0], "interest": names[1], "wire": names[2]}
    lot_codes = []
    for lot in s.non_assay_lots:
        codes = lookup.item([item.name for item in lot.items], s.books_code, log_loc)
        if isinstance(codes, tuple):
            return codes[1]
        lot_codes.append(codes)

    # Which invoices are needed
    classes = [[classify(code, invoicing) for code in codes] for codes in lot_codes]
    INV_PRIMARY = any(c in ("primary", "primary_override") for lot in classes for c in lot)
    INV_SECONDARY = any(c == "secondary" for lot in classes for c in lot)
    keep_desc = items_cfg["keep_description_keywords"]

    ### Begin QuickBooks connectivity ###
    sessionManager = qb.session_manager()
    print("QuickBooks opened.\n")
    sessionManager.OpenConnection(*qb.APP_SETTLEMENT)
    print("Connection opened.\n")
    try:
        sessionManager.BeginSession(comp, qb.OM_DONT_CARE)
        print("Session started.\n")
    except Exception:  # COM errors from QBFC
        easygui.exceptionbox(title=APP_TITLE)
        print("Error logged in log.txt\n")
        return logutil.entry(log_loc, MODULE, "FAILED", "Attempting to open QuickBooks company file",
                             ["Company file path: " + str(comp)])

    return_log = ""

    ## Purchase Order first
    requestMsgSet = qb.new_request(sessionManager)
    POAddRq = requestMsgSet.AppendPurchaseOrderAddRq()
    print("Requesting Purchase Order Add.\n")
    POAddRq.VendorRef.FullName.SetValue(ven_name)
    POAddRq.RefNumber.SetValue(contract_number)
    POAddRq.TxnDate.SetValue(inv_date)
    add_po = lambda **kw: po_line(POAddRq, **kw)
    add_assay_lines(add_po, s, metal_items, prefix)
    print("Paid-on-assay lines done!")
    for lot, codes in zip(s.non_assay_lots, lot_codes):
        if len(s.non_assay_lots) > 1:
            add_po(desc=lot.control_number)
        for item, code in zip(lot.items, codes):
            desc = item.name if _has_any(item.name, keep_desc) else None
            add_po(item=code, desc=desc, qty=item.pcs, rate=item.rate)
        add_po(desc=" ")
    print("Not-on-assay lines done!")
    add_fee_lines(add_po, s.fees, fee_items, prefix)
    print("PO done!")
    POresponseMsgSet = sessionManager.DoRequests(requestMsgSet)
    print("Request Set sent.\n")
    PO_OK = POresponseMsgSet.ResponseList.GetAt(0).StatusSeverity == "Info"

    ## Invoice(s) next, if the PO went off without a hitch
    PRIMARYresponseMsgSet = None
    SECONDARYresponseMsgSet = None
    if PO_OK and INV_PRIMARY:
        requestMsgSet = qb.new_request(sessionManager)
        invoiceAddRq = requestMsgSet.AppendInvoiceAddRq()
        print("Requesting Invoice Add (primary site).\n")
        cust_name = lookup.item([invoicing["primary"]["customer_key"]], s.books_code, log_loc)
        if isinstance(cust_name, tuple):
            qb.close(sessionManager)
            return cust_name[1]
        invoiceAddRq.CustomerRef.FullName.SetValue(cust_name[0])
        invoiceAddRq.PONumber.SetValue(contract_number)
        invoiceAddRq.TxnDate.SetValue(inv_date)
        add_inv = lambda **kw: invoice_line(invoiceAddRq, **kw)
        add_assay_lines(add_inv, s, metal_items, prefix)
        for lot, codes, kinds in zip(s.non_assay_lots, lot_codes, classes):
            if len(s.non_assay_lots) > 1:
                add_inv(desc=lot.control_number)
            for item, code, kind in zip(lot.items, codes, kinds):
                if kind == "primary":
                    desc = item.name if _has_any(item.name, keep_desc) else None
                    add_inv(item=code, desc=desc, qty=item.pcs, rate=item.rate)
                elif kind == "primary_override":
                    add_inv(item=code, qty=item.pcs, rate=item.rate)
            add_inv(desc=" ")
        add_fee_lines(add_inv, s.fees, fee_items, prefix)
        print("Primary site invoice done!")
        PRIMARYresponseMsgSet = sessionManager.DoRequests(requestMsgSet)
        print("Request Set sent.\n")

    if PO_OK and INV_SECONDARY:
        requestMsgSet = qb.new_request(sessionManager)
        invoiceAddRq = requestMsgSet.AppendInvoiceAddRq()
        print("Requesting Invoice Add (secondary site).\n")
        cust_name = lookup.item([invoicing["secondary"]["customer_key"]], s.books_code, log_loc)
        if isinstance(cust_name, tuple):
            qb.close(sessionManager)
            return cust_name[1]
        invoiceAddRq.CustomerRef.FullName.SetValue(cust_name[0])
        invoiceAddRq.PONumber.SetValue(contract_number)
        invoiceAddRq.TxnDate.SetValue(inv_date)
        add_inv = lambda **kw: invoice_line(invoiceAddRq, **kw)
        # A note linking this invoice to the primary invoice
        add_inv(desc="PORTION OF " + str(s.customer_name).upper() + " - " + contract_number)
        for lot, codes, kinds in zip(s.non_assay_lots, lot_codes, classes):
            if "secondary" in kinds:
                if len(s.non_assay_lots) > 1:
                    add_inv(desc=lot.control_number)
                for item, code, kind in zip(lot.items, codes, kinds):
                    if kind == "secondary":
                        add_inv(item=code, qty=item.pcs, rate=item.rate)
            add_inv(desc=" ")
        print("Secondary site invoice done!")
        SECONDARYresponseMsgSet = sessionManager.DoRequests(requestMsgSet)
        print("Request Set sent.\n")

    # Make a bill and link it to the PO we just made (if there was no error making said PO)
    BillresponseMsgSet = None
    if PO_OK:
        PODetail = POresponseMsgSet.ResponseList.GetAt(0).Detail
        requestMsgSet = qb.new_request(sessionManager)
        billAddRq = requestMsgSet.AppendBillAddRq()
        print("Requesting Bill Add.\n")
        billAddRq.VendorRef.FullName.SetValue(ven_name)
        billAddRq.RefNumber.SetValue(contract_number)
        billAddRq.LinkToTxnIDList.Add(PODetail.TxnID.GetValue())  # Link the bill to the PO
        billAddRq.TxnDate.SetValue(PODetail.TxnDate.GetValue())
        memo = []
        for response, site in ((PRIMARYresponseMsgSet, invoicing["primary"]), (SECONDARYresponseMsgSet, invoicing["secondary"])):
            if response is not None and response.ResponseList.GetAt(0).StatusSeverity == "Info":
                ref = response.ResponseList.GetAt(0).Detail.RefNumber.GetValue()
                memo.append(memo_tag(site["label"]) + " #" + str(ref))
        billAddRq.Memo.SetValue(", ".join(memo))
        BillresponseMsgSet = sessionManager.DoRequests(requestMsgSet)
        print("Request Set sent.\n")

    qb.close(sessionManager)

    ### Response Handling ###
    invoice_results = []
    for response in (PRIMARYresponseMsgSet, SECONDARYresponseMsgSet):
        if response is not None:
            ok, text = handle_response(response, "InvoiceAdd", contract_number, log_loc, print_invoice)
            invoice_results.append(ok)
            return_log += text
    INVSuccess = PO_OK and len(invoice_results) > 0 and all(invoice_results)

    POSuccess, text = handle_response(POresponseMsgSet, "PurchaseOrderAdd", contract_number, log_loc, print_purchase_order)
    return_log += text

    BILLSuccess = False
    if POSuccess:
        BILLSuccess, text = handle_response(BillresponseMsgSet, "BillAdd", contract_number, log_loc)
        return_log += text

    if INVSuccess and POSuccess and BILLSuccess:
        return_log += logutil.entry(log_loc, "Contract # " + contract_number, "SUCCESS",
                                    "Added invoice, purchase order, and bill to QuickBooks")
        if record.main(s.contract_number, s.payment_date[-4:], file) == 0:
            print("Task recorded!\n")

    print("All Done!\n")
    return return_log


def connect(file, log_loc):
    # Registers this module's AppID with the company file
    return qb_connect.authorize(file, log_loc, qb.APP_SETTLEMENT, MODULE)


if __name__ == "__main__":
    import easygui
    main(easygui.fileopenbox(), "log.txt")

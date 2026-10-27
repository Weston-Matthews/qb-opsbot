# qb-opsbot
# Bill comparison sub-module
# Written by Weston Matthews (2020)
# Takes the company file to search, the vendor, the transaction date, and the total amount to compare.
# If a bill from that vendor on that date matches the amount (within two cents), the settlement has already
# been entered: returns (1, log_text). Returns 0 when there is no match, or (-1, log_text) on an error.

from datetime import datetime

from qb_opsbot import logutil
from qb_opsbot import qb

MODULE = "QuickBooks Connect Module"
VIA = "By way of the Settlement Bill Comparison Sub-module"


def main(comp, vendor, inv_date, true_final_balance, log_loc):
    print("Running bill comparison sub-module...")
    print("Company file: " + str(comp))
    print("Vendor to compare: " + str(vendor))
    print("Date to compare: " + str(inv_date))
    print("Final balance: " + str(true_final_balance))

    ## Connect to the company file
    sessionManager = qb.session_manager()
    sessionManager.OpenConnection(*qb.APP_CONNECT)
    try:
        sessionManager.BeginSession(comp, qb.OM_DONT_CARE)
    except Exception:  # COM errors from QBFC (file missing, QuickBooks closed, not authorized...)
        import easygui as gui
        gui.exceptionbox()
        print("Error logged in log.txt\n")
        return (-1, logutil.entry(log_loc, MODULE, "FAILED", "Attempting to open QuickBooks company file",
                                  ["Company file path: " + str(comp)], via=VIA))

    ## Request a bill query for the date we have
    requestMsgSet = qb.new_request(sessionManager)
    billQueryRq = requestMsgSet.AppendBillQueryRq()
    txnDateFilter = billQueryRq.ORBillQuery.BillFilter.ORDateRangeFilter.TxnDateRangeFilter.ORTxnDateRangeFilter.TxnDateFilter
    txnDateFilter.FromTxnDate.SetValue(inv_date)
    txnDateFilter.ToTxnDate.SetValue(inv_date)
    responseMsgSet = sessionManager.DoRequests(requestMsgSet)

    # Disconnect from QuickBooks
    sessionManager.EndSession()
    sessionManager.CloseConnection()

    ## Cross-reference the bill info with the list of bills we get
    QueryRs = responseMsgSet.ResponseList.GetAt(0)
    statusSeverity = QueryRs.StatusSeverity

    if statusSeverity == "Info":
        billList = QueryRs.Detail
        if billList is None or len(billList) == 0:
            # There are no bills on this date, we're automatically good!
            print("No bills found in list!")
            return 0
        print("# of bills in list: " + str(len(billList)))
        true_final_balance = float(true_final_balance)
        for x in range(0, len(billList)):
            print("Comparing bill #" + str(x))
            bill = billList.GetAt(x)
            bill_vendor = bill.VendorRef.FullName.GetValue()
            bill_total = bill.AmountDue.GetValue()
            bill_date = bill.TxnDate.GetValue()
            bill_date = datetime(bill_date.year, bill_date.month, bill_date.day)
            print("Bill vendor: " + str(bill_vendor))
            print("Bill total: " + str(bill_total))
            print("Bill date: " + str(bill_date))
            print("Comparing: " + str(vendor) + " | " + str(bill_vendor))
            print("Comparing: " + str(inv_date) + " | " + str(bill_date))
            print("Comparing: " + str(true_final_balance - 0.02) + " <= " + str(bill_total) + " <= " + str(true_final_balance + 0.02))
            same_vendor = vendor == bill_vendor
            same_date = inv_date == bill_date
            same_amount = true_final_balance - 0.02 <= bill_total <= true_final_balance + 0.02
            if same_vendor and same_date and same_amount:
                # We have a match: log the info and pass the results on up
                return (1, logutil.entry(log_loc, MODULE, "SUCCESS", "Detected contract was already input into QuickBooks", [
                    "Bill Information:",
                    "     Taxation ID: " + str(bill.TxnID.GetValue()),
                    "     Reference Number: " + str(bill.RefNumber.GetValue()),
                    "     Vendor FullName: " + str(bill_vendor),
                    "     Date: " + str(bill_date),
                    "     Amount: " + str(bill_total),
                ], via=VIA))
        print("No matches found.")
        return 0
    elif statusSeverity == "Warning":
        # Can't be sure the settlement isn't already entered, so stop rather than risk a duplicate
        print("Warning logged in log.txt\n")
        return (-1, logutil.entry(log_loc, MODULE, "WARNING", details=logutil.status_details(
            QueryRs.StatusCode, statusSeverity, QueryRs.StatusMessage), via=VIA))
    else:
        print("Error logged in log.txt\n")
        return (-1, logutil.entry(log_loc, MODULE, "FAILED", details=logutil.status_details(
            QueryRs.StatusCode, statusSeverity, QueryRs.StatusMessage), via=VIA))


if __name__ == "__main__":
    print("Sub-module to be used only by the settlement module!")

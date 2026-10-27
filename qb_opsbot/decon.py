# qb-opsbot
# Deconstructor sub-module for the Invoice module
# Written by Weston Matthews (2020)
# Takes a bill object from the Invoice module and deconstructs it into pseudo-invoices:
# one for the whole bill, one for the lines that belong on the primary site's invoice,
# and one for the lines that belong on the secondary site's invoice.
# Pure Python: no QuickBooks or GUI dependencies.


### CLASS DEFINITIONS ###
class BillItem:
    def __init__(self, name):
        self.name = name
        self.desc = ""
        self.pcs = 0.00
        self.rate = 0.00
        self.total = 0.00

    def __str__(self):
        return (str(self.name) + " | " + str(self.desc) + " | " + str(self.pcs) + " | $" + str(self.rate) + " | $" + str(self.total) + "\n")


class ExpenseItem:
    def __init__(self):
        self.account = ""
        self.amount = 0.00
        self.memo = ""

    def __str__(self):
        return (str(self.account) + " | $" + str(self.amount) + " | '" + str(self.memo) + "'\n")


class LinkedTxn:
    # A transaction linked to a bill (normally its purchase order)
    def __init__(self, txnID):
        self.txnID = txnID
        self.txnDate = None
        self.refNumber = ""
        self.amount = 0.00
        self.txnType = ""
        self.linkType = ""

    def __str__(self):
        return (str(self.txnID) + " | " + str(self.refNumber) + " | " + str(self.txnDate) + " | $" + str(self.amount) + " | " + str(self.txnType) + " | " + str(self.linkType) + "\n")


class Bill:
    def __init__(self, txnID):
        self.txnID = txnID
        self.editSeq = ""
        self.vendorID = ""
        self.vendorName = ""
        self.refNumber = ""
        self.txnDate = None
        self.memo = ""
        self.isPaid = False
        self.amountDue = 0.00
        self.linkedPOs = []
        self.openAmount = 0.00
        self.lineItems = []
        self.expenses = []

    def __str__(self):
        POlist = "".join(str(PO) for PO in self.linkedPOs) or "None\n"
        lineItemList = "".join(str(item) for item in self.lineItems) or "No items\n"
        expList = "".join(str(exp) for exp in self.expenses) or "No expenses\n"
        return ("BILL: " + str(self.txnID) + "\n"
                "---------------------------------\n"
                "Reference Number: " + str(self.refNumber) + "\n"
                "Vendor FullName: " + str(self.vendorName) + "\n"
                "Vendor ID: " + str(self.vendorID) + "\n"
                "Taxation Date: " + str(self.txnDate) + "\n"
                "Amount Due: " + "$" + str(self.amountDue) + "\n"
                "Open Amount: " + "$" + str(self.openAmount) + "\n"
                "Is Paid: " + str(self.isPaid) + "\n"
                "Memo: '" + str(self.memo) + "'\n"
                "---------------------------------\n"
                "Associated Transactions:\n" + POlist +
                "---------------------------------\n"
                "Expenses:\n" + expList +
                "---------------------------------\n"
                "Line Items:\n" + lineItemList)

    def add_PO(self, txnID, txnDate, refNumber, amount, txnType, linkType):
        new_PO = LinkedTxn(txnID)
        new_PO.txnDate = txnDate
        new_PO.refNumber = refNumber
        new_PO.amount = amount
        new_PO.txnType = txnType
        new_PO.linkType = linkType
        self.linkedPOs.append(new_PO)
        print("PO " + str(txnID) + " added to bill " + str(self.txnID))

    def add_item(self, name, desc, pcs, rate, total):
        new_item = BillItem(name)
        new_item.desc = desc
        new_item.pcs = pcs
        new_item.rate = rate
        new_item.total = total
        self.lineItems.append(new_item)
        print("Item '" + str(name) + "' added to bill " + str(self.txnID))

    def add_expense(self, account, amount, memo):
        new_exp = ExpenseItem()
        new_exp.account = account
        new_exp.amount = amount
        new_exp.memo = memo
        self.expenses.append(new_exp)
        print("Expense added to bill " + str(self.txnID))


class InvoiceItem:
    def __init__(self, name):
        self.name = name
        self.desc = ""
        self.pcs = 0
        self.rate = 0
        self.total = 0

    def __str__(self):
        return (str(self.name) + " | " + str(self.desc) + " | " + str(self.pcs) + " | $" + str(self.rate) + " | $" + str(self.total) + "\n")


class Invoice:
    def __init__(self, txnID):
        self.txnID = txnID
        self.editSeq = ""
        self.txnNumber = ""
        self.custID = ""
        self.custName = ""
        self.refNumber = ""
        self.txnDate = None
        self.PONumber = ""
        self.memo = ""
        self.subtotal = 0.00
        self.balRemain = 0.00
        self.lineItems = []

    def __str__(self):
        lineItemList = "".join(str(item) for item in self.lineItems) or "No items\n"
        return ("INVOICE: " + str(self.txnID) + "\n"
                "---------------------------------\n"
                "Txn Number: " + str(self.txnNumber) + "\n"
                "Reference Number: " + str(self.refNumber) + "\n"
                "PO Number: " + str(self.PONumber) + "\n"
                "Customer FullName: " + str(self.custName) + "\n"
                "Customer ID: " + str(self.custID) + "\n"
                "Taxation Date: " + str(self.txnDate) + "\n"
                "Subtotal: " + "$" + str(self.subtotal) + "\n"
                "Balance Remaining: " + "$" + str(self.balRemain) + "\n"
                "Memo: '" + str(self.memo) + "'\n"
                "---------------------------------\n"
                "Line Items:\n" + lineItemList)

    def add_item(self, name, desc, pcs, rate, total):
        item = InvoiceItem(name)
        item.desc = desc
        item.pcs = pcs
        item.rate = rate
        item.total = total
        self.lineItems.append(item)


class Pseudo:
    # An invoice the bill implies, used to look for a matching real invoice before creating one
    def __init__(self, loc):
        self.loc = loc
        self.txnDate = None
        self.custName = ""
        self.PONumber = ""
        self.total = 0.00
        self.lineItems = []

    def __repr__(self):
        return "<Pseudo " + str(self.loc) + " $" + str(self.total) + " (" + str(len(self.lineItems)) + " lines)>"

    def add_item(self, name, desc, pcs, rate, total):
        item = InvoiceItem(name)
        item.desc = desc
        item.pcs = pcs
        item.rate = rate
        item.total = total
        self.lineItems.append(item)


def _has_any(text, fragments):
    return any(fragment in text for fragment in fragments)


def _pseudo(loc, bill, customer, items, total):
    p = Pseudo(loc)
    p.txnDate = bill.txnDate
    p.custName = customer
    p.PONumber = bill.refNumber
    p.lineItems = items
    p.total = total
    return p


def main(bill, cust_primary, cust_secondary, primary_prefixes, secondary_prefixes):
    # Returns (whole, primary, secondary); primary/secondary are None when the bill has no lines for them
    primary_items = []
    secondary_items = []

    # Figure out how many invoices need to be created
    for item in bill.lineItems:
        if _has_any(item.name, primary_prefixes):
            primary_items.append(item)
        elif _has_any(item.name, secondary_prefixes):
            secondary_items.append(item)

    # The whole pseudo is always created
    whole = _pseudo("whole", bill, cust_primary, bill.lineItems, bill.amountDue)
    primary = None
    secondary = None
    if primary_items:
        primary = _pseudo("primary", bill, cust_primary, primary_items, float(sum(item.total for item in primary_items)))
    if secondary_items:
        secondary = _pseudo("secondary", bill, cust_secondary, secondary_items, float(sum(item.total for item in secondary_items)))
    return (whole, primary, secondary)


if __name__ == "__main__":
    print("Sub-module cannot be accessed outside of Invoice module!")

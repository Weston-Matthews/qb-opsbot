# qb-opsbot
# Settlement statement parser
# Written by Weston Matthews (2020)
#
# Reads a refiner's settlement statement (an Excel workbook) into plain Python objects.
# A statement has three kinds of sections:
#   * paid-on-assay lots   - precious metals (Pt / Pd / Rh) paid by troy ounce, possibly in several breakdown rows
#   * not-on-assay lots    - items paid by piece count and rate
#   * fees                 - treatment charge, advance payments with their interest and wire fees,
#                            and the interest and wire fee on the final payment
# followed by the final balance due and the books code it belongs to.
#
# This module has no QuickBooks or GUI dependencies. `sheet` is anything with the xlrd Sheet
# interface: .nrows, .ncols and .cell_value(row, col). Where things sit on the sheet comes from
# the "settlement_layout" section of the config.

from datetime import date, timedelta

from qb_opsbot import settings

METALS = (("Pt", "Platinum (Pt)"), ("Pd", "Palladium (Pd)"), ("Rh", "Rhodium  (Rh)"))


### CLASS DEFINITIONS ###
class AssayLot:
    # Metals paid on assay for one lab control number
    def __init__(self, control_number):
        self.control_number = control_number
        self.Pt_vals = []
        self.Pd_vals = []
        self.Rh_vals = []
        self.total = 0.00

    def __str__(self):
        lines = ""
        for symbol, label in METALS:
            for item in self.values(symbol):
                lines += label + " | " + str(item[0]) + " | " + "$" + str(item[1]) + "\n"
        return ("Paid on assay: " + str(self.control_number) + "\n"
                "--------------------------\n" + lines + "Total: " + "$" + str(self.total))

    def values(self, symbol):
        return {"Pt": self.Pt_vals, "Pd": self.Pd_vals, "Rh": self.Rh_vals}[symbol]

    def add_val(self, symbol, Toz, total):
        self.values(symbol).append((Toz, total))
        self.recalc_total()

    def add_Pt_val(self, Toz, total):
        self.add_val("Pt", Toz, total)

    def add_Pd_val(self, Toz, total):
        self.add_val("Pd", Toz, total)

    def add_Rh_val(self, Toz, total):
        self.add_val("Rh", Toz, total)

    def recalc_total(self):
        self.total = sum(val[1] for val in self.Pt_vals + self.Pd_vals + self.Rh_vals)


class NonAssayItem:
    def __init__(self, name):
        self.name = name
        self.pcs = 0
        self.rate = 0.00
        self.total = 0.00

    def __str__(self):
        return (str(self.name) + " | " + str(self.pcs) + " | " + "$" + str(self.rate) + " | " + "$" + str(self.total) + "\n")

    def set_pcs(self, value):
        self.pcs = float(value)
        self.recalc_total()

    def set_rate(self, value):
        self.rate = float(value)
        self.recalc_total()

    def set_total(self, value):
        self.total = float(value)
        self.recalc_rate()

    def recalc_total(self):
        self.total = self.pcs * self.rate

    def recalc_rate(self):
        self.rate = self.total / self.pcs


class NonAssayLot:
    # Items not paid on assay (priced per piece) for one lab control number
    def __init__(self, control_number):
        self.control_number = control_number
        self.items = []
        self.total = 0.00

    def __str__(self):
        item_str = "".join(str(item) for item in self.items)
        return ("Not on assay: " + str(self.control_number) + "\n"
                "---------------------------------\n"
                "\n" + item_str + "\n"
                "TOTAL: " + "$" + str(self.total) + "\n")

    def add_item(self, name, pcs=0, rate=0.00, total=0.00):
        item = NonAssayItem(name)
        item.set_pcs(pcs)
        item.set_rate(rate)
        if total != 0.00:
            item.set_total(total)
        self.items.append(item)
        self.recalc_total()

    def recalc_total(self):
        if self.items != []:
            self.total = sum(item.total for item in self.items)


class AdvanceFees:
    def __init__(self, index):
        self.index = index
        self.payment = 0.00
        self.interest = 0.00
        self.wire = 0.00
        self.total = 0.00

    def __str__(self):
        return ("Less Advance Payment: " + "$" + str(self.payment) + "\n"
                "Interest on Advance Payment: " + "$" + str(self.interest) + "\n"
                "Wire Transfer Fee (Advance): " + "$" + str(self.wire) + "\n")

    def set_payment(self, value):
        self.payment = value
        self.recalc_total()

    def set_interest(self, value):
        self.interest = value
        self.recalc_total()

    def set_wire(self, value):
        self.wire = value
        self.recalc_total()

    def recalc_total(self):
        self.total = float(self.payment) + float(self.interest) + float(self.wire)


class Fees:
    def __init__(self):
        self.treatment_charge = 0.00
        self.advances = []
        self.advance_index = 0
        self.final_interest = 0.00
        self.final_wire = 0.00
        self.total = 0.00

    def __str__(self):
        advs_str = "".join(str(adv) for adv in self.advances)
        return ("FEES:\n"
                "---------------------------------------------------\n"
                "Treatment Charge: " + "$" + str(self.treatment_charge) + "\n"
                "\n" + advs_str + "\n"
                "Interest on Final Payment: " + "$" + str(self.final_interest) + "\n"
                "Wire Transfer Fee (Final): " + "$" + str(self.final_wire) + "\n")

    def set_treatment(self, value):
        self.treatment_charge = value
        self.recalc_total()

    def set_interest(self, value):
        self.final_interest = value
        self.recalc_total()

    def set_wire(self, value):
        self.final_wire = value
        self.recalc_total()

    def add_advance(self):
        adv = AdvanceFees(self.advance_index)
        self.advances.append(adv)
        self.advance_index += 1
        self.recalc_total()
        return adv

    def advance_total(self):
        return sum(adv.total for adv in self.advances)

    def adv_payment_total(self):
        return sum(adv.payment for adv in self.advances)

    def recalc_total(self):
        self.total = float(self.treatment_charge) + float(self.final_interest) + float(self.final_wire) + self.advance_total()


class Settlement:
    def __init__(self):
        self.books_code = ""          # Which set of books the statement belongs to
        self.contract_number = ""
        self.customer_name = ""       # Printed as "Customer" on the statement; it is the vendor in QuickBooks
        self.payment_date = ""        # MM/DD/YYYY
        self.final_balance = 0.00
        self.true_final_balance = 0.00  # Final balance plus every advance already paid
        self.assay_lots = []
        self.non_assay_lots = []
        self.fees = Fees()

    def item_names(self):
        return [item.name for lot in self.non_assay_lots for item in lot.items]

    def __str__(self):
        text = ("Books Code: " + str(self.books_code) + "\n"
                "Contract Number: " + str(self.contract_number) + "\n"
                "Customer Name: " + str(self.customer_name) + "\n"
                "Payment Date: " + str(self.payment_date) + "\n\n")
        for lot in self.assay_lots + self.non_assay_lots:
            text += str(lot) + "\n\n"
        text += str(self.fees) + "\n"
        text += "Final Balance Due: " + "$" + "{0:.2f}".format(self.final_balance) + "\n"
        text += "True Final Balance: " + "$" + "{0:.2f}".format(self.true_final_balance) + "\n"
        return text


### FUNCTION DEFINITIONS ###
def convert_date(s):
    # Converts an Excel date serial number to MM/DD/YYYY
    days = int(s) - 2  # Excel's serial 60 is the non-existent 29 Feb 1900; dates before March 1900 are off by one
    offset = date(1900, 1, 1) + timedelta(days)
    return "{:02d}/{:02d}/{}".format(offset.month, offset.day, offset.year)


def calc_true_balance(fees, final_balance):
    # The final balance has the advances already subtracted; add them back to get the full contract value
    return final_balance + -1 * fees.adv_payment_total()


def _matches(cell_data, label):
    if isinstance(label, (list, tuple)):
        return any(one in cell_data for one in label)
    return label in cell_data


def _read_metal(sheet, lot, symbol, j_row, j_col, layout, last):
    # Reads one metal starting at j_row (the row with the metal's name). If the row below the name is blank
    # in the label column, the metal is split into several breakdown rows that each carry an amount.
    a = layout["assay"]
    qty_col = j_col + a["qty_col_offset"]
    amt_col = j_col + a["amount_col_offset"]
    if last:
        # Rhodium is the last metal: a breakdown exists unless the TOTAL label is two rows down
        breakdown = sheet.cell_value(j_row + 2, j_col + a["total_label_col_offset"]) != layout["labels"]["assay_total"]
    else:
        breakdown = sheet.cell_value(j_row + 1, j_col) == ''
    if breakdown:
        j_row += 1
        while True:
            toz = float(sheet.cell_value(j_row, qty_col))
            tot = float(sheet.cell_value(j_row, amt_col))
            lot.add_val(symbol, float(format(toz, '.5f')), float(format(tot, '.2f')))
            j_row += 1
            if sheet.cell_value(j_row, j_col) != '':
                break
    else:
        toz = float(sheet.cell_value(j_row, qty_col))
        tot = float(sheet.cell_value(j_row, amt_col))
        lot.add_val(symbol, float(format(toz, '.5f')), float(format(tot, '.2f')))
        j_row += 1
    return j_row


def parse_settlement(sheet, layout=None):
    # Scans the sheet left to right, top to bottom, and fills a Settlement from the labelled sections
    if layout is None:
        layout = settings.load_config()["settlement_layout"]
    labels = layout["labels"]
    value_col = layout["value_col"]
    s = Settlement()
    cur_control_num = ""  # The current lab control number, used to name each lot

    for i_row in range(sheet.nrows):
        for i_col in range(sheet.ncols):
            cell_data = str(sheet.cell_value(i_row, i_col))
            if labels["contract_number"] in cell_data:
                s.contract_number = sheet.cell_value(i_row, value_col)
            elif labels["customer"] in cell_data:
                customer_name = sheet.cell_value(i_row + layout["customer_row_offset"], i_col)
                if customer_name[:1] == ' ':
                    customer_name = customer_name[1:]  # Get rid of the space that's always there
                s.customer_name = customer_name
            elif labels["payment_date"] in cell_data:
                s.payment_date = convert_date(sheet.cell_value(i_row, value_col))
            elif labels["lot_control"] in cell_data:
                cur_control_num = sheet.cell_value(i_row, i_col + 1)
            elif _matches(cell_data, labels["assay_section"]):
                lot = AssayLot(cur_control_num)
                # Platinum's name sits first_row_offset rows below the section heading, then Palladium, then Rhodium
                j_row = i_row + layout["assay"]["first_row_offset"]
                j_row = _read_metal(sheet, lot, "Pt", j_row, i_col, layout, last=False)
                j_row = _read_metal(sheet, lot, "Pd", j_row, i_col, layout, last=False)
                _read_metal(sheet, lot, "Rh", j_row, i_col, layout, last=True)
                s.assay_lots.append(lot)
            elif _matches(cell_data, labels["non_assay_section"]):
                lot = NonAssayLot(cur_control_num)
                n = layout["non_assay"]
                j_row = i_row + n["first_row_offset"]
                while sheet.cell_value(j_row, n["name_col"]) != "":
                    lot.add_item(sheet.cell_value(j_row, n["name_col"]),
                                 sheet.cell_value(j_row, n["qty_col"]),
                                 sheet.cell_value(j_row, n["rate_col"]))
                    j_row += 1
                s.non_assay_lots.append(lot)
            elif _matches(cell_data, labels["fees_section"]):
                f = layout["fees"]
                j_row = i_row + f["row_offset"]
                j_col = i_col + f["label_col_offset"]
                v_col = j_col + f["value_col_offset"]
                while True:
                    label = str(sheet.cell_value(j_row, j_col))
                    if labels["fees_end"] in label:
                        break
                    elif labels["treatment_charge"] in label:
                        s.fees.set_treatment(sheet.cell_value(j_row, v_col))
                    elif labels["advance_payment"] in label:
                        adv = s.fees.add_advance()
                        adv.set_payment(sheet.cell_value(j_row, v_col))
                        adv.set_interest(sheet.cell_value(j_row + 1, v_col))
                        adv.set_wire(sheet.cell_value(j_row + 2, v_col))
                    elif labels["final_interest"] in label:
                        s.fees.set_interest(sheet.cell_value(j_row, v_col))
                    elif labels["final_wire"] in label:
                        s.fees.set_wire(sheet.cell_value(j_row, v_col))
                    j_row += 1
            elif labels["final_balance"] in cell_data:
                s.final_balance = sheet.cell_value(i_row, value_col)
                s.true_final_balance = calc_true_balance(s.fees, s.final_balance)
                s.books_code = sheet.cell_value(i_row, layout["books_code_col"])
    return s

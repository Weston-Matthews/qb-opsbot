# Parses a settlement statement and prints what the bot would enter, without touching QuickBooks.
#   python samples/parse_statement.py samples/sample_statement.xlsx
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import xlrd  # noqa: E402

from qb_opsbot import settings  # noqa: E402
from qb_opsbot.contract import classify  # noqa: E402
from qb_opsbot import lookup  # noqa: E402
from qb_opsbot.settlement import parse_settlement  # noqa: E402


def main(path):
    config = settings.load_config()
    layout = config["settlement_layout"]
    sheet = xlrd.open_workbook(path).sheet_by_index(layout["sheet_index"])
    s = parse_settlement(sheet, layout)
    print(s)
    log = os.devnull
    print("Vendor in QuickBooks: " + str(lookup.vendor(s.customer_name, log)))
    codes = lookup.item(s.item_names(), s.books_code, log)
    if isinstance(codes, tuple):
        print(codes[1])
        return
    for name, code in zip(s.item_names(), codes):
        print("  " + name + "  ->  " + code + "  [" + str(classify(code, config["invoicing"])) + "]")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "sample_statement.xlsx"))

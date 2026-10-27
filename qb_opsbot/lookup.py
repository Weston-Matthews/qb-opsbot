# qb-opsbot
# Lookup module
# Written by Weston Matthews (2020)
# Looks up QuickBooks names in two small reference tables (CSV or Excel):
#   vendor list - name as printed on a settlement statement -> QuickBooks vendor FullName
#   item map    - generic item name -> QuickBooks item FullName, one column per books code
# Lookups that fail return a (1, log_text) tuple, which callers pass straight up to the user.

import csv
import os
import zipfile
import os.path as path

from qb_opsbot import APP_TITLE
from qb_opsbot import logutil
from qb_opsbot import settings

MODULE = "qb-opsbot Lookup Module"

# Everything load_table can raise for a missing, locked or malformed file
TABLE_ERRORS = (OSError, ValueError, KeyError, IndexError, ImportError, zipfile.BadZipFile)


def load_table(file_path):
    # Returns the first sheet of a .csv, .xlsx or .xls file as a list of rows of strings
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".csv":
        with open(file_path, "r", newline="", encoding="utf-8-sig") as file:
            return [[cell for cell in row] for row in csv.reader(file)]
    if ext in (".xlsx", ".xlsm"):
        import openpyxl
        wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
        ws = wb.worksheets[0]
        rows = [["" if cell is None else str(cell) for cell in row] for row in ws.iter_rows(values_only=True)]
        wb.close()
        return rows
    import xlrd
    try:
        sheet = xlrd.open_workbook(file_path).sheet_by_index(0)
    except xlrd.XLRDError as err:
        raise ValueError(str(err))
    return [[str(sheet.cell_value(r, c)) for c in range(sheet.ncols)] for r in range(sheet.nrows)]


def _cell(rows, r, c):
    row = rows[r]
    return row[c] if c < len(row) else ""


def _open_failed(log_loc, what, file_path):
    if path.exists(file_path):
        detail = what + " file path: " + str(file_path)
    else:
        detail = "No " + what + " found!"
    text = logutil.entry(log_loc, MODULE, "FAILED", "Attempting to open " + what, [detail])
    print("Error logged in log.txt\n")
    return (1, text)


# Takes two arguments, name, the name of a vendor, and log_loc, the file path of the log
# Reads the vendor list and returns the QuickBooks FullName from the list
# Returns the name back if not found in the list
def vendor(name, log_loc, config=None):
    config = config or settings.load_config()
    vendor_loc = config.path("vendor_list")
    try:
        rows = load_table(vendor_loc)
        print("Vendor database opened.\n")
    except TABLE_ERRORS:
        return _open_failed(log_loc, "Vendor list", vendor_loc)

    for r in range(len(rows)):
        if str(_cell(rows, r, 0)) == name:
            full_name = _cell(rows, r, 1)
            if full_name != '':
                return full_name
            print("No entry found for vendor '" + name + "'.")
            return name

    print("Did not find name in vendor list.")
    return name


def normalize_item_name(item_name, config=None):
    # Collapses item names that carry extra detail (e.g. "Sample Weight - Lot 7") to their canonical name
    config = config or settings.load_config()
    for rule in config["items"]["name_normalization"]:
        if rule["contains"] in item_name:
            return rule["canonical"]
    return item_name


# Takes three arguments: a list of item names, the books code, and the file path of the log
# Reads the item map and returns the item FullNames for that books code, in the same order
# Returns (1, log_text) if the map, the column, or any item is missing
def item(item_list, books_code, log_loc, config=None):
    config = config or settings.load_config()
    dict_loc = config.path("item_map")
    try:
        rows = load_table(dict_loc)
        print("Item database opened.\n")
    except TABLE_ERRORS:
        return _open_failed(log_loc, "item map", dict_loc)

    books_code = settings.resolve_books_code(books_code, config)
    header = rows[0] if rows else []
    if books_code not in header[1:]:
        text = logutil.entry(log_loc, MODULE, "FAILED",
                             "Searching for column for books code: " + str(books_code),
                             ["Note: Column missing!"])
        print("Did not find '" + str(books_code) + "' in list of code names.")
        return (1, text)
    code_num = header.index(books_code, 1)

    return_list = []
    for entry_name in item_list:
        item_name = normalize_item_name(entry_name.strip(), config)
        print("Searching item map for '" + str(item_name) + "'")
        found = False
        for r in range(1, len(rows)):
            if str(_cell(rows, r, 0)) == item_name:
                full_name = _cell(rows, r, code_num)
                if full_name != '':
                    return_list.append(full_name)
                    found = True
                    break
                text = logutil.entry(log_loc, MODULE, "FAILED",
                                     "Searching for item '" + str(item_name) + "' in column '" + str(books_code) + "'",
                                     ["Note: No entry for specified item!"])
                print("No entry found for item '" + item_name + "' for book code '" + books_code + "'.")
                return (1, text)
        if not found:
            text = logutil.entry(log_loc, MODULE, "FAILED", "Searching for item '" + str(item_name) + "'",
                                 ["Note: Item not in list!"])
            print("Item '" + str(item_name) + "' not found in the list!")
            return (1, text)

    return return_list


def books_code_for_file(file_path, config=None):
    # Returns the books code whose configured company file has the same file name, or None
    config = config or settings.load_config()
    file_name = file_path[max(file_path.rfind("\\"), file_path.rfind("/")) + 1:]
    for code, book in config["books"].items():
        company_file = book.get("company_file", "")
        if company_file and company_file[max(company_file.rfind("\\"), company_file.rfind("/")) + 1:] == file_name:
            return code
    return None


# Takes one argument, path, the file path of the company file, as a string
# Returns the books code of the company file (asks the user if it isn't configured), or 0 if cancelled
def main(file_path, config=None):
    config = config or settings.load_config()
    choices = list(config["books"].keys())
    if file_path[-4:] in ['.qbw', '.QBW']:
        # It is a QuickBooks company file
        code = books_code_for_file(file_path, config)
        if code is not None:
            print(code)
            return code
        print("Could not find company file in list!")
        msg = "Book code was not found in the list.\nPlease select the books code to use."
    else:
        print("Incorrect QB company file path!")
        msg = "File selected was not a QB company file.\nPlease select the books code to use."
    import easygui as gui
    selected = gui.choicebox(msg, APP_TITLE, choices)
    if selected == [] or selected is None:
        # Go back to the selection list
        return 0
    return selected


if __name__ == "__main__":
    import easygui as gui
    gui.msgbox("Please select a company file to look up.", APP_TITLE, ok_button='OK')
    main(gui.fileopenbox())

# qb-opsbot
# Command module
# Written by Weston Matthews (2020)
# Graphical menu that ties the jobs together: pick a job, pick files, and see a summary of what happened.

import os

import easygui as gui

from qb_opsbot import APP_TITLE
from qb_opsbot import settings

JOB_CONNECT = "(QB) Connect to a company file to ask for authorization"
JOB_SETTLEMENT = "(QB) Convert settlement spreadsheet into PO, Bill, and Invoice"
JOB_INVOICE = "(QB) Create Invoices for uninvoiced Bills"
JOB_OPTIONS = "Options"
OTHER_FILE = "Select another company file"


def log_location(config):
    log_loc = config.path("log_file")
    os.makedirs(os.path.dirname(log_loc), exist_ok=True)
    if not os.path.exists(log_loc):
        open(log_loc, 'w').close()
    return log_loc


def run_settlements(title, log_loc):
    msg = "Please select the settlement spreadsheet(s) to be input into QuickBooks.\n\n(To select multiple files, hold Ctrl while selecting.)"
    gui.msgbox(msg, title, ok_button='OK')
    loc = gui.fileopenbox(msg="Select the settlement spreadsheet(s)", title=title, multiple=True)
    if loc is None:
        print("Cancelled file selection.")
        return
    print("File path(s) confirmed.\n")
    from qb_opsbot import contract
    log = ""
    for file in loc:
        log += contract.main(file, log_loc)
    gui.textbox("I'm all done! Here's what happened:", title, text=log)


def run_invoicer(title, log_loc):
    gui.msgbox("Please select the QuickBooks company file to use.", title, ok_button='OK')
    file = gui.fileopenbox("Please select the QuickBooks company file to use", title)
    if file is None:
        print("Cancelled file selection.")
        return
    print("File path confirmed.\n")
    from qb_opsbot import invoicer
    ret_log = invoicer.main(file, log_loc)
    if ret_log == 0:
        pass
    elif type(ret_log) == str:
        gui.textbox("I'm all done! Here's what happened:", title, text=ret_log)
    else:
        gui.exceptionbox(title=title)


def run_connect(title, log_loc, config, current):
    # Offers the company files configured for this machine's server profile, plus a file picker
    codes = config["server_profiles"].get(current.profile, [])
    books = config["books"]
    files = {}
    for code in codes:
        if code in books:
            files[books[code].get("label", code)] = books[code].get("company_file", "")
    while True:
        choices = list(files.keys()) + ["", OTHER_FILE] if files else [OTHER_FILE]
        if len(choices) == 1:
            choices = choices + [""]  # easygui's choicebox needs at least two choices
        choice = gui.choicebox("Please select the QuickBooks company file to connect to.", title, choices)
        if choice is None:
            return
        if choice == "":
            continue
        if choice == OTHER_FILE:
            file = gui.fileopenbox(msg="Select the company file", title=title)
            if file is None:
                continue
        else:
            file = files[choice]
        print("File path confirmed.\n")
        # QuickBooks authorizes each AppID separately, so register every module
        from qb_opsbot import connect, contract, invoicer
        log = connect.main(file, log_loc)
        log += contract.connect(file, log_loc)
        log += invoicer.connect(file, log_loc)
        gui.textbox("I'm all done! Here's what happened:", title, text=log)
        return


def run_options(title, log_loc, config, current):
    if current.debug:
        choices = ["Toggle debug setting", "Set server location", "Open the log", "Output log as an external file"]
    else:
        choices = ["Toggle debug setting", "Set server location"]
    option = gui.choicebox('', title, choices)
    if option == "Toggle debug setting":
        default = "ON" if current.debug else "OFF"
        opt = gui.buttonbox("Debug mode", title, ["OFF", "ON"], default_choice=default, cancel_choice=default)
        if opt in ("ON", "OFF"):
            current.debug = (opt == "ON")
            settings.save_settings(current, config)
    elif option == "Set server location":
        profiles = list(config["server_profiles"].keys())
        opt = gui.buttonbox("What server am I installed on?", title, profiles,
                            default_choice=current.profile, cancel_choice=current.profile)
        if opt in profiles:
            current.profile = opt
            settings.save_settings(current, config)
    elif option == "Open the log":
        with open(log_loc, 'r') as file:
            text = file.read()
        gui.textbox("Here's the log:", title, text=text)
    elif option == "Output log as an external file":
        os.startfile(log_loc)  # Windows only: opens the log in the default text editor


def main():
    config = settings.load_config()
    current = settings.load_settings(config)
    log_loc = log_location(config)
    title = APP_TITLE

    # Job selection list
    while True:
        choices = [JOB_CONNECT, JOB_SETTLEMENT, JOB_INVOICE, "", JOB_OPTIONS]
        choice = gui.choicebox("What job would you like me to do?", title, choices)
        if choice == JOB_SETTLEMENT:
            run_settlements(title, log_loc)
        elif choice == JOB_INVOICE:
            run_invoicer(title, log_loc)
        elif choice == JOB_CONNECT:
            run_connect(title, log_loc, config, current)
        elif choice == "":
            pass
        elif choice == JOB_OPTIONS:
            run_options(title, log_loc, config, current)
        elif choice is None:
            break
        else:
            print("Error occurred: Invalid job selection choice.")
            break


if __name__ == "__main__":
    main()

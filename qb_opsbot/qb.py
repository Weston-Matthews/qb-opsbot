# qb-opsbot
# QuickBooks (QBFC13 SDK) session helpers
# Written by Weston Matthews (2020)
# win32com is imported lazily, so the pure-Python modules (parsing, lookups, tests) work on any OS.

from qb_opsbot import __version__

# QBFC13 ENOpenMode values
OM_SINGLE_USER = 0
OM_MULTI_USER = 1
OM_DONT_CARE = 2

# AppID / AppName pairs QuickBooks uses to remember each module's authorization.
# The Connect ID is shared by helper modules and sub-modules that support the main job modules.
APP_CONNECT = ("QBOPSBOT_CON_v1", "qb-opsbot Connect v" + __version__)
APP_SETTLEMENT = ("QBOPSBOT_SETTLE_v1", "qb-opsbot Settlement v" + __version__)
APP_INVOICE = ("QBOPSBOT_INV_v1", "qb-opsbot Invoice v" + __version__)


def session_manager():
    # Opens the QBFC COM session manager (requires Windows, QuickBooks Desktop and the QBFC13 SDK)
    import win32com.client as win32
    return win32.DispatchEx("QBFC13.QBSessionManager")


def new_request(session):
    # US edition, qbXML 7.0
    return session.CreateMsgSetRequest("US", 7, 0)


def close(session):
    session.EndSession()           # Close the company file
    print("Session ended. Company file closed.\n")
    session.CloseConnection()      # Close the connection
    print("Connection closed.\n")


def print_status(response):
    print("Status Code: " + str(response.StatusCode))
    print("Status Severity: " + str(response.StatusSeverity))
    print("Status Message: " + str(response.StatusMessage))
    print("\n")

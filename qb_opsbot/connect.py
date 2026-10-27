# qb-opsbot
# Connect module
# Written by Weston Matthews (2020)
# Connects to a QuickBooks company file so QuickBooks shows its authorization dialog for each module.
# QuickBooks remembers authorization per AppID, so the menu runs this once per module (see authorize()).

from qb_opsbot import APP_TITLE
from qb_opsbot import logutil
from qb_opsbot import qb

MODULE = "QuickBooks Connect Module"


def authorize(file, log_loc, app, module):
    # Opens a session with the given (AppID, AppName) to trigger/confirm authorization, then logs the
    # authorization preferences QuickBooks reports. Returns the log text.
    sessionManager = qb.session_manager()
    print("QuickBooks opened.\n")
    sessionManager.OpenConnection(*app)
    print("Connection opened.\n")
    try:
        sessionManager.BeginSession(file, qb.OM_DONT_CARE)
        print("Session started.\n")
    except Exception:  # COM errors from QBFC
        print("Error logged in log.txt\n")
        return logutil.entry(log_loc, module, "FAILED", "Attempting to open QuickBooks company file",
                             ["Company file path: " + str(file)])

    authpref = sessionManager.QBAuthPreferences
    readonly = authpref.GetIsReadOnly()
    unattmode = authpref.GetUnattendedModePref()
    persdata = authpref.GetPersonalDataPref()
    print("Authorizations")
    print("Read only: " + str(readonly))
    print("Unattended mode: " + str(unattmode))
    print("Personal data: " + str(persdata))
    print("")
    qb.close(sessionManager)

    return logutil.entry(log_loc, module, "SUCCESS", "Connected to QuickBooks and received authorization", [
        "Company file path: " + str(file),
        "Authorization Preferences:",
        "     Read Only: " + str(readonly),
        "     Unattended Mode: " + str(unattmode),
        "     Personal Data: " + str(persdata),
    ])


def _host_lines(QueryRet):
    versionList = []
    qbxmlVerList = QueryRet.SupportedQBXMLVersionList
    for x in range(0, int(qbxmlVerList.GetMaxLength())):
        versionList.append(qbxmlVerList.GetAt(x))
    info = [
        ("Product Name", QueryRet.ProductName.GetValue()),
        ("Version", str(QueryRet.MajorVersion.GetValue()) + "." + str(QueryRet.MinorVersion.GetValue())),
        ("Country", QueryRet.Country.GetValue()),
        ("QBXML Supported Versions", versionList),
        ("Automatic Login", QueryRet.IsAutomaticLogin.GetValue()),
        ("File Mode", QueryRet.QBFileMode.GetAsString()),
    ]
    for label, value in info:
        print(label + ": " + str(value))
    return ["Host Query:"] + ["     " + label + ": " + str(value) for label, value in info]


# Connects to a QB company file in order to trigger the authorization dialog, and reports the QuickBooks version
# Takes the file path of the QB company file and the log path; returns a string log of what happened
def main(file, log_loc):
    print("Initialized.\n")
    sessionManager = qb.session_manager()
    print("QuickBooks opened.\n")
    sessionManager.OpenConnection(*qb.APP_CONNECT)
    print("Connection opened.\n")
    try:
        sessionManager.BeginSession(file, qb.OM_DONT_CARE)
        print("Session started.\n")
    except Exception:  # COM errors from QBFC
        import easygui as gui
        gui.exceptionbox()
        print("Error logged in log.txt\n")
        return logutil.entry(log_loc, MODULE, "FAILED", "Attempting to open QuickBooks company file",
                             ["Company file path: " + str(file)])

    # Read the AuthPreferences object
    authpref = sessionManager.QBAuthPreferences
    print("Authorizations")
    print("Read only: " + str(authpref.GetIsReadOnly()))
    print("Unattended mode: " + str(authpref.GetUnattendedModePref()))
    print("Personal data: " + str(authpref.GetPersonalDataPref()))
    print("")

    # Requesting a HostQuery, to get info on the QB version
    requestMsgSet = qb.new_request(sessionManager)
    requestMsgSet.AppendHostQueryRq()
    print("Requesting Host Query.\n")
    responseMsgSet = sessionManager.DoRequests(requestMsgSet)
    print("Request Set sent.\n")
    qb.close(sessionManager)

    QueryRs = responseMsgSet.ResponseList.GetAt(0)
    print("Printing HostQuery response information:\n")
    qb.print_status(QueryRs)
    status = logutil.status_details(QueryRs.StatusCode, QueryRs.StatusSeverity, QueryRs.StatusMessage)

    return_log = ""
    if QueryRs.StatusSeverity == "Info":
        return_log = logutil.entry(log_loc, MODULE, "SUCCESS", "Connected to QuickBooks and obtained authorization",
                                   _host_lines(QueryRs.Detail))
    elif QueryRs.StatusSeverity == "Warning":
        return_log = logutil.entry(log_loc, MODULE, "WARNING", "Attempting to connect to QuickBooks and obtain authorization",
                                   status + _host_lines(QueryRs.Detail))
    elif QueryRs.StatusSeverity == "Error":
        return_log = logutil.entry(log_loc, MODULE, "FAILED", "Attempting to connect to QuickBooks and obtain authorization",
                                   status)
        print("Error logged in log.txt\n")

    print("All Done!\n")
    return return_log


if __name__ == "__main__":
    import easygui as gui
    gui.msgbox("Please select a QB file to connect to.", APP_TITLE, ok_button='OK')
    main(gui.fileopenbox(), "log.txt")

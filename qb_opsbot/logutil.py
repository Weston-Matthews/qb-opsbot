# qb-opsbot
# Shared logging helpers
# Written by Weston Matthews (2020)
# Every module reports what it did twice: once to the log file, and once as text shown to the user.
# These helpers do both in one call so the format stays identical everywhere.

from datetime import datetime

SEPARATOR = "------------------------------------"


def timestamp():
    return str(datetime.now())


def write_block(log_loc, lines):
    # Appends a block of lines to the log file, followed by the separator, and returns the same text
    text = "".join(str(line) + "\n" for line in lines) + SEPARATOR + "\n" + "\n"
    with open(log_loc, "a") as file:
        file.write(text)
    return text


def entry(log_loc, module, status, action=None, details=(), via=None):
    # Standard log entry:
    #   <module>
    #   [<via>]
    #   Timestamp: ...
    #   Status: SUCCESS | WARNING | FAILED
    #   [Action: ...]
    #   <details...>
    lines = [module]
    if via:
        lines.append(via)
    lines.append("Timestamp: " + timestamp())
    lines.append("Status: " + status)
    if action:
        lines.append("Action: " + action)
    lines.extend(details)
    return write_block(log_loc, lines)


def status_details(code, severity, message):
    # The three status fields every QBFC response carries
    return ["Status Code: " + str(code),
            "Status Severity: " + str(severity),
            "Status Message: " + str(message)]


class RunLog:
    # For modules that report line by line (e.g. one line per bill): every write goes to the log file
    # and is kept in .text for the summary shown to the user
    def __init__(self, log_loc):
        self.log_loc = log_loc
        self.text = ""

    def write(self, text):
        with open(self.log_loc, "a") as file:
            file.write(text)
        self.text += text

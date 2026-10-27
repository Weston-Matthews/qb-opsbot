# qb-opsbot
# Screening sub-module
# Written by Weston Matthews (2020)
# Takes a vendor name and a list of item names, then checks the item map and the vendor list
# to make sure the settlement can be entered.
# Returns 0 if all is good, else the (1, log_text) error tuple from the lookup module.

from qb_opsbot import lookup


def main(customer_name, total_item_list, books_code, log_loc):
    ven_conf = lookup.vendor(customer_name, log_loc)
    if not isinstance(ven_conf, str):
        # An error was passed, pass it on
        print("Error found during screening\n")
        return ven_conf

    item_conf = lookup.item(total_item_list, books_code, log_loc)
    if isinstance(item_conf, tuple):
        # An error was raised, pass it on up
        print("Error found during screening\n")
        return item_conf

    print("Done with screening!\n")
    return 0


if __name__ == "__main__":
    print("This module is to be used exclusively by the settlement module.")

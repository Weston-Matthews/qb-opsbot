# qb-opsbot
# Configuration and runtime settings
# Written by Weston Matthews (2020)
#
# config.json   - everything site-specific: company files, books codes, data file paths,
#                 the settlement statement layout, item routing rules (see config.example.json)
# settings.json - the two values the Options menu changes at runtime: server profile and debug mode
#
# Relative paths in config.json are resolved against the folder that holds config.json.

import copy
import json
import os
import sys

CONFIG_NAME = "config.json"
EXAMPLE_CONFIG_NAME = "config.example.json"
SETTINGS_NAME = "settings.json"

# Defaults for every key the code reads. config.json only needs to override what differs.
DEFAULT_CONFIG = {
    "default_profile": "TEST",
    "paths": {
        "vendor_list": "data/vendors.example.csv",
        "item_map": "data/item_map.example.csv",
        "contract_summary_workbook": "",
        "log_file": "log/log.txt",
    },
    # books code -> {"label": shown in menus, "company_file": QuickBooks .qbw path}
    "books": {},
    # alternate books codes that should be treated as another code
    "book_aliases": {},
    # server profile -> books codes offered in the "Connect" menu on that machine
    "server_profiles": {"TEST": []},
    # Where each value sits on the settlement statement (0-based rows/columns, as read by xlrd)
    "settlement_layout": {
        "sheet_index": 2,
        "value_col": 7,
        "books_code_col": 1,
        "customer_row_offset": 2,
        "labels": {
            "contract_number": "Contract Number",
            "customer": "Customer:",
            "payment_date": "Payment Date",
            "lot_control": "Lab Control",
            "assay_section": ["Paid on Assay", "Purchased on Assay"],
            "assay_total": "TOTAL ",
            "non_assay_section": "Not on Assay",
            "fees_section": "Fees",
            "fees_end": "TOTAL",
            "treatment_charge": "Treatment Charge",
            "advance_payment": "Less Advance Payment",
            "final_interest": "Interest on Final Payment",
            "final_wire": "Wire Transfer Fee (Final)",
            "final_balance": "FINAL BALANCE DUE",
        },
        "assay": {"first_row_offset": 2, "qty_col_offset": 4, "amount_col_offset": 6, "total_label_col_offset": 5},
        "non_assay": {"first_row_offset": 2, "name_col": 4, "qty_col": 5, "rate_col": 6},
        "fees": {"row_offset": 1, "label_col_offset": 4, "value_col_offset": 1},
    },
    "items": {
        # item-map keys for the three assayed metals and the three fee types
        "assay_metals": {"Pt": "Assay Pt", "Pd": "Assay Pd", "Rh": "Assay Rh"},
        "fees": {"treatment": "Treatment Charge", "interest": "Interest Charge", "wire": "Wire Fee"},
        # prefix for generated line descriptions, e.g. "Assay- Pt 1.25 oz Contract # 1001 01/31/2020"
        "line_desc_prefix": "Assay-",
        # an item whose name contains "contains" is looked up as "canonical" (first match wins)
        "name_normalization": [],
        # keep the original item name as the line description when it contains one of these
        "keep_description_keywords": [],
    },
    "invoicing": {
        "primary": {"label": "Primary Site", "customer_key": "custPrimary"},
        "secondary": {"label": "Secondary Site", "customer_key": "custSecondary"},
        # QuickBooks item FullName fragments that route a line to each site's invoice
        "primary_item_prefixes": [],
        "secondary_item_prefixes": [],
        # secondary-prefixed items that still go on the primary invoice (settlement module only)
        "primary_override_keywords": [],
        "generated_by": "qb-opsbot",
    },
    "record": {"contract_col": "C", "done_col": "J", "link_col": "Q"},
}


def app_dir():
    # Folder holding the .exe when frozen by PyInstaller, otherwise the repository root
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def find_config():
    # config.json in the working directory, then next to the app; falls back to config.example.json
    for name in (CONFIG_NAME, EXAMPLE_CONFIG_NAME):
        for folder in (os.getcwd(), app_dir()):
            candidate = os.path.join(folder, name)
            if os.path.exists(candidate):
                if name == EXAMPLE_CONFIG_NAME:
                    print("No " + CONFIG_NAME + " found, using " + EXAMPLE_CONFIG_NAME)
                return candidate
    return None


def _merge(base, override):
    # Recursive dict merge; lists and scalars in override replace the default
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = value
    return result


class Config(dict):
    # A dict with the folder it was loaded from, used to resolve relative paths
    def __init__(self, data, base_dir):
        super().__init__(data)
        self.base_dir = base_dir

    def path(self, key):
        value = self["paths"].get(key, "")
        if not value:
            return ""
        if os.path.isabs(value) or value.startswith("\\\\"):
            return value
        return os.path.join(self.base_dir, value)


_cached = None


def load_config(path=None, reload=False):
    global _cached
    if _cached is not None and path is None and not reload:
        return _cached
    if path is None:
        path = find_config()
    if path is None:
        data, base_dir = copy.deepcopy(DEFAULT_CONFIG), os.getcwd()
    else:
        with open(path, "r", encoding="utf-8") as file:
            data = _merge(DEFAULT_CONFIG, json.load(file))
        base_dir = os.path.dirname(os.path.abspath(path))
    config = Config(data, base_dir)
    _cached = config
    return config


def resolve_books_code(code, config=None):
    config = config or load_config()
    return config["book_aliases"].get(code, code)


class Settings:
    def __init__(self, profile, debug):
        self.profile = profile
        self.debug = debug


def settings_path(config=None):
    config = config or load_config()
    return os.path.join(config.base_dir, SETTINGS_NAME)


def load_settings(config=None):
    # Never raises: a missing or unreadable settings file falls back to defaults and is rewritten
    config = config or load_config()
    path = settings_path(config)
    default = Settings(config["default_profile"], False)
    try:
        with open(path, "r", encoding="utf-8") as file:
            data = json.load(file)
        return Settings(str(data.get("profile", default.profile)), bool(data.get("debug", False)))
    except (OSError, ValueError, AttributeError):
        try:
            save_settings(default, config)
        except OSError:
            pass
        return default


def save_settings(settings, config=None):
    with open(settings_path(config), "w", encoding="utf-8") as file:
        json.dump({"profile": settings.profile, "debug": settings.debug}, file, indent=2)

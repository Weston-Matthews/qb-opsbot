import importlib
import os

from qb_opsbot import lookup, settings


def test_vendor_lookup(config, log_loc):
    assert lookup.vendor("Acme Salvage Co", log_loc, config) == "Acme Salvage Co."
    assert lookup.vendor("Unknown Vendor", log_loc, config) == "Unknown Vendor"


def test_item_lookup_normalizes_and_uses_books_column(config, log_loc):
    names = lookup.item(["Widget Core - Large", "Sample Weight - Lot 7", " Copper Scrap "], "BOOK-A", log_loc, config)
    assert names == ["Converters:WCL", "Converters:Sample Wgt", "Metals:Cu"]


def test_item_lookup_alias(config, log_loc):
    assert lookup.item(["Copper Scrap"], "BOOK-A2", log_loc, config) == ["Metals:Cu"]


def test_item_lookup_errors_are_logged(config, log_loc):
    missing = lookup.item(["Not An Item"], "NORTH", log_loc, config)
    assert missing[0] == 1 and "Item not in list!" in missing[1]
    empty = lookup.item(["Mixed Lot"], "BOOK-A", log_loc, config)
    assert empty[0] == 1 and "No entry for specified item!" in empty[1]
    no_col = lookup.item(["Copper Scrap"], "NOPE", log_loc, config)
    assert no_col[0] == 1 and "Column missing!" in no_col[1]
    assert "Status: FAILED" in open(log_loc).read()


def test_books_code_for_file(config):
    assert lookup.books_code_for_file("Z:\\copy\\Site North.qbw", config) == "NORTH"
    assert lookup.books_code_for_file("Z:\\copy\\Elsewhere.qbw", config) is None


def test_missing_settings_file_uses_defaults(tmp_path):
    # Previously the settlement module crashed on import when its settings file was missing
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text('{"default_profile": "Region 1"}')
    config = settings.load_config(str(cfg_path), reload=True)
    current = settings.load_settings(config)
    assert current.profile == "Region 1" and current.debug is False
    assert os.path.exists(settings.settings_path(config))   # written with defaults
    (tmp_path / "settings.json").write_text("not json")
    assert settings.load_settings(config).profile == "Region 1"


def test_modules_import_without_quickbooks():
    # No win32com, no settings file, no GUI needed just to import the job modules
    for name in ("contract", "invoicer", "connect", "bill_check", "record", "screening"):
        importlib.import_module("qb_opsbot." + name)

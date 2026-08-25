from apps.worker.ingestion.dart_client import map_induty_to_sector


def test_map_induty_to_sector_prefers_longer_prefix():
    # "264"(반도체)는 "26"(전기전자)보다 우선한다
    assert map_induty_to_sector("26410") == "반도체"


def test_map_induty_to_sector_falls_back_to_two_digit_prefix():
    assert map_induty_to_sector("30120") == "자동차"
    assert map_induty_to_sector("64110") == "은행"


def test_map_induty_to_sector_unknown_code_is_none():
    assert map_induty_to_sector("99999") is None


def test_map_induty_to_sector_handles_missing_input():
    assert map_induty_to_sector(None) is None
    assert map_induty_to_sector("") is None

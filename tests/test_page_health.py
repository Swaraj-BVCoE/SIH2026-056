from scraper.browser import _storage_state_path


def test_browser_state_is_isolated_and_sanitized():
    air_india = _storage_state_path("air_india_direct")
    makemytrip = _storage_state_path("makemytrip")
    unsafe = _storage_state_path("../../bad source")

    assert air_india != makemytrip
    assert air_india.parent.name == "browser_states"
    assert unsafe.parent.name == "browser_states"
    assert unsafe.name == "bad_source.json"

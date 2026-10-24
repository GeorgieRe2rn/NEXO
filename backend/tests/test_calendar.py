from datetime import datetime, timezone

from app.domain.identity import club_fits_league
from app.etl.calendar import (
    current_season_year,
    is_in_season,
    is_visible_upcoming,
    kickoff_iso,
    kickoff_is_upcoming,
    roll_kickoff,
)


def _dt(y, m, d, hh=12):
    return datetime(y, m, d, hh, 0, tzinfo=timezone.utc)


def test_european_leagues_off_in_june():
    june = _dt(2026, 6, 15)
    for code in ("PL", "PD", "SA"):
        assert is_in_season(code, june) is False
        assert is_in_season(code, _dt(2026, 9, 21)) is True
        assert is_in_season(code, _dt(2027, 1, 10)) is True


def test_liga_mx_off_in_june():
    assert is_in_season("MX", _dt(2026, 6, 10)) is False
    assert is_in_season("MX", _dt(2026, 9, 21)) is True
    assert is_in_season("MX", _dt(2027, 3, 1)) is True


def test_mls_off_in_january():
    assert is_in_season("MLS", _dt(2026, 1, 20)) is False
    assert is_in_season("MLS", _dt(2026, 9, 21)) is True
    assert is_in_season("MLS", _dt(2026, 11, 20)) is True


def test_season_year_wraps():
    assert current_season_year("PL", _dt(2026, 9, 21)) == 2026
    assert current_season_year("PL", _dt(2027, 3, 1)) == 2026
    assert current_season_year("MX", _dt(2027, 2, 1)) == 2026
    assert current_season_year("MLS", _dt(2026, 9, 21)) == 2026


def test_roll_kickoff_lands_in_the_future():
    now = _dt(2026, 9, 21, 18)
    rolled = roll_kickoff("2026-09-19T23:00:00+00:00", now)
    assert rolled > now
    assert rolled.weekday() == 5  # sábado, igual que el 19


def test_old_catalog_dates_are_not_upcoming():
    now = _dt(2026, 9, 21, 20)
    past = datetime(2026, 9, 19, 23, 0, tzinfo=timezone.utc)
    assert kickoff_is_upcoming(past, now) is False
    assert is_visible_upcoming(past, "SCHEDULED", now) is False


def test_scheduled_kickoff_in_the_past_is_hidden():
    now = _dt(2026, 9, 21, 18)
    kick = datetime(2026, 9, 21, 2, 30, tzinfo=timezone.utc)
    assert is_visible_upcoming(kick, "SCHEDULED", now) is False


def test_kickoff_iso_marks_utc():
    dt = datetime(2026, 9, 21, 2, 30)
    assert kickoff_iso(dt).endswith("+00:00")


def test_display_window_covers_the_last_local_evening_and_utc_next_day():
    from app.etl.calendar import display_window, scoreboard_dates
    start,end=display_window(_dt(2026,10,16,7))
    assert start==_dt(2026,10,16,7)
    assert end==_dt(2026,10,26,7)
    assert start < _dt(2026,10,26,3) < end  # 25 oct, 20:00 Hermosillo
    assert "20261026" in scoreboard_dates(_dt(2026,10,16,7))
    assert "20261027" not in scoreboard_dates(_dt(2026,10,16,7))


def test_display_window_changes_on_hermosillo_midnight():
    from app.etl.calendar import display_window
    assert display_window(_dt(2026,10,16,6))[0]==_dt(2026,10,15,7)
    assert display_window(_dt(2026,10,16,7))[0]==_dt(2026,10,16,7)


def test_chivas_is_not_chicago_fire():
    assert club_fits_league("Chivas Guadalajara", "MX") is True
    assert club_fits_league("Chicago Fire", "MX") is False
    assert club_fits_league("Chicago Fire", "MLS") is True
    assert club_fits_league("Club América", "MX") is True
    assert club_fits_league("Inter Miami", "SA") is False
    assert club_fits_league("Inter Miami", "MLS") is True

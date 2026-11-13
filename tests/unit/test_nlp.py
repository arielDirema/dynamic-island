"""Quick-entry parsing in English and French."""
import datetime as dt

from dynamic_island.engines import nlp


NOW = dt.datetime(2026, 11, 12, 10, 0)  # Thursday


def test_relative_date_and_time():
    out = nlp.parse("Réunion demain 14h30", now=NOW)
    assert out["title"] == "Réunion"
    assert out["date"] == dt.date(2026, 11, 13)
    assert out["time"] == dt.time(14, 30)


def test_priority_project_and_weekday():
    out = nlp.parse("Appeler Paul lundi !haute #travail", now=NOW)
    assert out["title"] == "Appeler Paul"
    assert out["date"] == dt.date(2026, 11, 16)
    assert out["priority"] == 3
    assert out["project"] == "travail"


def test_day_of_month_duration_and_birthday():
    out = nlp.parse("Dentiste le 5 à 9h pendant 30min", now=NOW)
    assert out["title"] == "Dentiste"
    assert out["date"] == dt.date(2026, 12, 5)
    assert out["time"] == dt.time(9, 0)
    assert out["duration"] == 30

    birthday = nlp.parse("Anniversaire Marie 12/03", now=NOW)
    assert birthday["birthday"] is True
    assert birthday["date"] == dt.date(2027, 3, 12)
    assert birthday["title"] == "Anniversaire Marie"


def test_evening_default_and_title_cleanup():
    out = nlp.parse("ce soir cinéma", now=NOW)
    assert out["date"] == dt.date(2026, 11, 12)
    assert out["time"] == dt.time(20, 0)
    assert out["title"] == "Cinéma"


def test_parse_duration():
    assert nlp.parse_duration("25") == 25 * 60
    assert nlp.parse_duration("10m") == 10 * 60
    assert nlp.parse_duration("1h30") == 90 * 60
    assert nlp.parse_duration("90s") == 90
    assert nlp.parse_duration("1:30") == 90
    assert nlp.parse_duration("") is None
    assert nlp.parse_duration("invalid") is None


def test_english_relative_date_and_time():
    out = nlp.parse("Meeting tomorrow 2:30 pm", now=NOW)
    assert out["title"] == "Meeting"
    assert out["date"] == dt.date(2026, 11, 13)
    assert out["time"] == dt.time(14, 30)


def test_english_priority_project_and_weekday():
    out = nlp.parse("Call Paul next Monday !high #work", now=NOW)
    assert out["title"] == "Call Paul"
    assert out["date"] == dt.date(2026, 11, 16)
    assert out["priority"] == 3
    assert out["project"] == "work"


def test_english_day_of_month_duration_and_birthday():
    out = nlp.parse("Dentist on the 5th at 9am for 30 minutes", now=NOW)
    assert out["title"] == "Dentist"
    assert out["date"] == dt.date(2026, 12, 5)
    assert out["time"] == dt.time(9, 0)
    assert out["duration"] == 30

    birthday = nlp.parse("Marie birthday March 12", now=NOW)
    assert birthday["birthday"] is True
    assert birthday["date"] == dt.date(2027, 3, 12)


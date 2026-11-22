from exp4_day import Item, Schedule, best, check

VALID = [("Borghese Gallery", "09:00", "11:00"), ("Lunch", "12:00", "13:00"), ("Colosseum", "14:00", "16:00"),
         ("Pantheon", "16:30", "17:30"), ("Trastevere food walk", "18:00", "19:30")]


def day(*rows):
    return Schedule(items=[Item(name=n, start=s, end=e) for n, s, e in rows])


def replace(name, start, end):
    return day(*[(n, start, end) if n == name else (n, s, e) for n, s, e in VALID])


def test_accepts_a_valid_day():
    assert check(day(*VALID)) == []


def test_rejects_a_missing_move():
    errors = check(day(("Colosseum", "09:00", "11:00"), ("Borghese Gallery", "11:00", "13:00"),
                       ("Lunch", "13:30", "14:30"), ("Pantheon", "15:00", "16:00"),
                       ("Trastevere food walk", "17:00", "18:30")))
    assert errors == ["Colosseum -> Borghese Gallery: needs 30 min to move"]


def test_rejects_a_start_off_the_hour():
    assert "Colosseum: cannot start at 14:30" in check(replace("Colosseum", "14:30", "16:30"))


def test_rejects_a_wrong_duration():
    assert "Pantheon: lasts 90 min, must be 60" in check(replace("Pantheon", "16:30", "18:00"))


def test_rejects_lunch_outside_its_window():
    assert "Lunch: cannot start at 14:30" in check(replace("Lunch", "14:30", "15:30"))


def test_rejects_the_food_walk_at_the_wrong_time():
    assert "Trastevere food walk: cannot start at 18:30" in check(replace("Trastevere food walk", "18:30", "20:00"))


def test_rejects_a_missing_and_a_duplicated_item():
    errors = check(day(*VALID[:4], ("Pantheon", "18:00", "19:00")))
    assert "Trastevere food walk appears 0 times" in errors
    assert "Pantheon appears 2 times" in errors


def test_rejects_an_unknown_spelling():
    errors = check(day(*[("colosseum" if n == "Colosseum" else n, s, e) for n, s, e in VALID]))
    assert "unknown item 'colosseum'" in errors
    assert "Colosseum appears 0 times" in errors


def test_rejects_a_bad_time_format():
    assert "Lunch: bad time format" in check(replace("Lunch", "noon", "13:00"))


def test_rejects_a_day_that_starts_too_early():
    assert "outside 09:00-20:00" in check(replace("Borghese Gallery", "08:00", "10:00"))


def test_best_prefers_the_latest_start():
    later = day(("Pantheon", "09:30", "10:30"), ("Borghese Gallery", "11:00", "13:00"), ("Lunch", "13:30", "14:30"),
                ("Colosseum", "15:00", "17:00"), ("Trastevere food walk", "18:00", "19:30"))
    assert check(later) == []
    samples = [(day(*VALID), [], 0), (later, [], 0), (None, ["unparseable output"], 0)]
    assert best(samples) is later
    assert best([(None, ["unparseable output"], 0)]) is None
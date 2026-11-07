import pytest

from registration.fields import clean_email, clean_name, clean_phone


@pytest.mark.parametrize("raw, expected", [
    ("ANDI PRATAMA", "Andi Pratama"),
    ("siti nur aisyah", "Siti Nur Aisyah"),
    ("Andi  Pratama ", "Andi Pratama"),                    # mixed case is left as typed, spaces collapsed
    ("NISA YU'TIKA", "Nisa Yu'Tika"),
    ("AHMAD AR-RASYID", "Ahmad Ar-Rasyid"),
    ("budi santoso iii", "Budi Santoso III"),
    ("Ahmad M. Ali", "Ahmad M. Ali"),                      # an initial is not a degree
])
def test_student_name_case(raw, expected):
    assert clean_name(raw, student=True)[0] == expected


def test_student_name_loses_degrees_but_accompanying_person_keeps_them():
    name, notes = clean_name("Siti Nur, S.Pd", student=True)
    assert name == "Siti Nur" and [c for c, _ in notes] == ["name_title_removed"]
    assert clean_name("Dr. Rina Wati, M.Pd", student=True)[0] == "Rina Wati"
    assert clean_name("Endang Astuti, S.Pd", student=False) == ("Endang Astuti, S.Pd", [])


def test_stray_characters_digits_and_single_words_are_noted():
    name, notes = clean_name("Andi \U0001F600 Pratama!", student=True)
    assert name == "Andi Pratama" and [c for c, _ in notes] == ["name_chars"]
    assert [c for c, _ in clean_name("Andi 2", student=True)[1]] == ["name_digits"]
    assert [c for c, _ in clean_name("Andi", student=True)[1]] == ["name_single_word"]
    assert clean_name("Andi", student=False)[1] == []


@pytest.mark.parametrize("raw, expected", [
    ("081234567890", "081234567890"),
    ("+62 812-3456-7890", "081234567890"),
    ("6281234567890", "081234567890"),
    ("81234567890", "081234567890"),                       # leading 0 lost by Excel
    (81234567890.0, "081234567890"),                       # numeric cell
])
def test_phone_forms_become_one_form(raw, expected):
    assert clean_phone(raw) == (expected, [])


def test_phone_with_two_numbers_keeps_the_first_and_short_numbers_are_noted():
    assert clean_phone("081234567890 / 081298765432") == ("081234567890", [("phone_multiple", "several numbers, the first is kept")])
    assert [c for c, _ in clean_phone("0812345")[1]] == ["phone_length"]
    assert clean_phone("-") == ("", [])


def test_email_follows_the_html_standard_and_the_rfc_5321_lengths():
    bad = ["a..b@example.com@", "a@b", "@example.com", "a@-example.com", "a@example-.com", "a@exa_mple.com", "a@example..com",
           "é@example.com", "a" * 65 + "@example.com", "a@" + "b" * 64 + ".com", "a@" + ".".join(["b" * 60] * 5) + ".com"]
    good = ["andi.test@example.com", "a+b@example.co.id", "o'brien@example.com", "x@a-b.example.com", "a" * 64 + "@example.com", "sitinur2025@sekolah.sch.id"]
    assert [e for e in bad if not [c for c, _ in clean_email(e)[1] if c == "invalid_email"]] == []
    assert [e for e in good if [c for c, _ in clean_email(e)[1] if c == "invalid_email"]] == []


def test_email_is_lowercased_and_checked():
    assert clean_email(" Andi.Test@Example.COM ") == ("andi.test@example.com", [])
    assert [c for c, _ in clean_email("andi.example.com")[1]] == ["invalid_email"]
    assert [c for c, _ in clean_email("andi@gmial.com")[1]] == ["email_domain_typo"]
    email, notes = clean_email("a@example.com; b@example.com")
    assert email == "a@example.com" and [c for c, _ in notes] == ["email_multiple"]


def test_brackets_and_excel_control_character_artifacts_are_removed():
    name, notes = clean_name("Fina Nailatul Izzah (Slamet)", student=True)
    assert name == "Fina Nailatul Izzah" and [c for c, _ in notes] == ["name_brackets"]
    assert clean_name("Ade Nugraha Sudarsono, S.Kom_x0000_", student=False) == ("Ade Nugraha Sudarsono, S.Kom", [])


def test_two_numbers_separated_by_spaces_are_two_numbers():
    phone, notes = clean_phone("081234567890  081298765432")
    assert phone == "081234567890" and [c for c, _ in notes] == ["phone_multiple"]

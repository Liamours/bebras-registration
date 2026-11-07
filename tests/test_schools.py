import pandas as pd
import pytest

from registration import schools

MASTER = pd.DataFrame(
    [
        ["smp_negeri_1_pacet", "SMP Negeri 1 Pacet", "20200001", "SMP", "Kabupaten Bandung", "SMPN 1 Pacet"],
        ["sd_negeri_5_sukajadi", "SD Negeri 5 Sukajadi", "20200002", "SD", "Kota Bandung", ""],
        ["sma_islam_serang", "SMA Islam Serang", "", "SMA", "other", ""],
    ],
    columns=schools.MASTER_COLUMNS,
)


@pytest.mark.parametrize(
    "typed, expected",
    [
        ("SMPN 1 PACET", "SMP Negeri 1 Pacet"),
        ("smpn 1pacet", "SMP Negeri 1 Pacet"),
        ("SDN 5 Sukajadi", "SD Negeri 5 Sukajadi"),
        ("MTsN 2 Bandung", "MTs Negeri 2 Bandung"),
        ("SMP PLUS AL-AITAAM", "SMP Plus Al-Aitaam"),
        ("SDII AL ABIDIN YOGYAKARTA", "SDII Al Abidin Yogyakarta"),
        ("  SMA   Telkom Bandung ", "SMA Telkom Bandung"),
    ],
)
def test_canonical_name_rules(typed, expected):
    assert schools.canonical(typed) == expected


def test_punctuation_and_case_do_not_make_two_schools():
    assert schools.key("SMP Mathla'ul Anwar Margahayu") == schools.key("SMP MATHLAUL ANWAR MARGAHAYU")
    assert schools.key("SMPN 1 Pacet") == schools.key("SMP Negeri 1 Pacet")


def test_lookup_by_name_and_alias_and_suggestion_is_never_picked():
    found, _ = schools.lookup("SMPN 1 PACET", MASTER)
    assert found["school_slug"] == "smp_negeri_1_pacet"
    none, suggestions = schools.lookup("SMP Negeri 1 Pacett", MASTER)  # one letter off: suggested, not picked
    assert none is None and suggestions == ["SMP Negeri 1 Pacet"]
    none, suggestions = schools.lookup("SMA Lain Sekali", MASTER)
    assert none is None and suggestions == []


def students(*rows):
    return pd.DataFrame(rows, columns=["Nama Sekolah", "Kota/Kabupaten"])


def test_matched_school_gets_canonical_name_slug_and_region():
    table, review = schools.canonicalize(students(["SMPN 1 PACET", "Bandung"], ["SDN 5 Sukajadi", "BANDUNG"], ["SMA Islam Serang", "Serang"]), MASTER)
    assert list(table["Nama Sekolah"]) == ["SMP Negeri 1 Pacet", "SD Negeri 5 Sukajadi", "SMA Islam Serang"]
    assert list(table["Kota/Kabupaten"]) == ["Kabupaten Bandung", "Kota Bandung", "Serang"]  # the region `other` keeps what the sender wrote
    assert list(table["school_slug"]) == ["smp_negeri_1_pacet", "sd_negeri_5_sukajadi", "sma_islam_serang"] and review.empty


def test_unknown_school_is_reported_with_suggestions_and_a_bare_bandung_with_both_candidates():
    table, review = schools.canonicalize(students(["SMPN 1 Pacett", "Bandung"], ["SMP Baru", "Cimahi"]), MASTER)
    assert list(table["Nama Sekolah"]) == ["SMP Negeri 1 Pacett", "SMP Baru"] and list(table["Kota/Kabupaten"]) == ["Bandung", "Kota Cimahi"]  # the school is not guessed; a city that names one region is written in full
    got = {(r["check"], r["school"]): r["suggestions"] for _, r in review.iterrows()}
    assert got[("region_ambiguous", "SMPN 1 Pacett")] == "Kota Bandung | Kabupaten Bandung"
    assert got[("school_unmatched", "SMP Negeri 1 Pacett")] == "SMP Negeri 1 Pacet" and got[("school_unmatched", "SMP Baru")] == "-"


def test_master_from_the_list_and_the_files_keeps_existing_folders_and_marks_other_schools():
    portal = pd.DataFrame([["20200001", "SMP NEGERI 1 PACET", "", "", "NEGERI", "SMP", "Kabupaten Bandung", "Pacet", "2026-11-07"],
                           ["20200003", "SMP MATHLAUL ANWAR MARGAHAYU", "", "", "SWASTA", "SMP", "Kabupaten Bandung", "Margahayu", "2026-11-07"]],
                          columns=["npsn", "name", "address", "kelurahan", "status", "jenjang", "region", "kecamatan", "fetched"])
    seen = pd.DataFrame([["SMPN 1 PACET", "SMP", "Kab. Bandung"], ["SMP Mathla'ul Anwar Margahayu", "SMP", "Kab. Bandung"], ["SMA Islam Serang", "SMA", "Serang"]], columns=["name", "jenjang", "city"])
    hand = pd.DataFrame([["Pacet 1", "20200001"]], columns=["alias", "npsn"])
    master, added = schools.build_master(portal, seen, hand, {"smpmathlaulanwarmargahayu": "smp_mathla_ul_anwar_margahayu"})
    by_name = master.set_index("canonical_name")
    assert by_name.loc["SMP Mathlaul Anwar Margahayu", "school_slug"] == "smp_mathla_ul_anwar_margahayu"  # the folder that exists is not renamed
    assert by_name.loc["SMP Negeri 1 Pacet", "aliases"] == "Pacet 1|SMPN 1 PACET"
    assert by_name.loc["SMA Islam Serang", "region"] == "other" and list(added["seen_name"]) == ["SMA Islam Serang"]
    assert not master["school_slug"].duplicated().any()


SHARED = pd.DataFrame(
    [
        ["sd_negeri_1_a", "SD Negeri 1", "30000001", "SD", "Kota Bandung", ""],
        ["sd_negeri_1_b", "SD Negeri 1", "30000002", "SD", "Kabupaten Bandung", ""],
        ["smp_negeri_19", "SMP Negeri 19", "30000003", "SMP", "Kota Bandung", ""],
        ["smk_negeri_1_cimahi_a", "SMK Negeri 1", "30000004", "SMK", "Kota Cimahi", ""],
    ],
    columns=schools.MASTER_COLUMNS,
)


def test_a_name_shared_by_several_schools_is_not_picked_but_the_city_narrows_it():
    none, suggestions = schools.lookup("SDN 1", SHARED)
    assert none is None and len(suggestions) == 2 and "NPSN 30000001" in suggestions[0]  # both candidates are shown, none is chosen
    found, _ = schools.lookup("SDN 1", SHARED, city="Kab. Bandung")
    assert found["npsn"] == "30000002"
    found, _ = schools.lookup("SDN 1", SHARED, city="Kota Bandung")
    assert found["npsn"] == "30000001"
    none, _ = schools.lookup("SDN 1", SHARED, city="Bandung")  # a bare Bandung leaves both Kota and Kabupaten possible
    assert none is None


def test_the_city_a_sender_adds_at_the_end_is_dropped_when_the_list_has_no_city():
    found, _ = schools.lookup("SMPN 19 BANDUNG", SHARED)
    assert found["npsn"] == "30000003"
    found, _ = schools.lookup("SMKN 1 Cimahi", SHARED)
    assert found["npsn"] == "30000004"
    none, _ = schools.lookup("SMPN 19 Cimahi", SHARED)  # the other city: a different school, nothing matched
    assert none is None


def test_regions_a_typed_city_can_mean():
    assert schools.regions_of("Kab. Bandung") == ("Kabupaten Bandung",) and schools.regions_of("KAB.BANDUNG BARAT") == ("Kabupaten Bandung Barat",)
    assert schools.regions_of("Bandung") == ("Kota Bandung", "Kabupaten Bandung") and schools.regions_of("Kota Cimahi") == ("Kota Cimahi",)
    assert schools.regions_of("Serang") == () and schools.regions_of("") == ()


def test_a_typed_city_that_contradicts_the_matched_school_is_reported():
    table, review = schools.canonicalize(students(["SMPN 1 Pacet", "Kota Bandung"], ["SMPN 1 Pacet", "Kab. Bandung"]), MASTER)
    assert list(table["Kota/Kabupaten"]) == ["Kabupaten Bandung", "Kabupaten Bandung"]
    assert [(r["check"], r["value"], r["rows"]) for _, r in review.iterrows()] == [("region_conflict", "Kota Bandung -> Kabupaten Bandung", 1)]


def test_other_spellings_of_the_state_school_prefix_and_numbers():
    for typed in ["SMP N 1 Pacet", "SMPN.1 Pacet", "SMP NEGERI 01 PACET", "smpn1pacet"]:
        assert schools.canonical(typed) == "SMP Negeri 1 Pacet", typed
    assert schools.canonical("SMP Negeri 100 Bandung") == "SMP Negeri 100 Bandung"  # only leading zeros go
    found, _ = schools.lookup("SMPN 19 Kab. Bandung", SHARED.assign(region=["Kota Bandung", "Kabupaten Bandung", "Kabupaten Bandung", "Kota Cimahi"]))
    assert found["npsn"] == "30000003"  # the ending `Kab. Bandung` is read as the region Kabupaten Bandung


def test_master_does_not_add_a_name_without_a_place():
    portal = pd.DataFrame([["20200001", "SMP NEGERI 1 PACET", "", "", "NEGERI", "SMP", "Kabupaten Bandung", "Pacet", "2026-11-07"]],
                          columns=["npsn", "name", "address", "kelurahan", "status", "jenjang", "region", "kecamatan", "fetched"])
    seen = pd.DataFrame([["SDN 1", "SD", "Bandung"], ["SMA Islam Serang", "SMA", "Serang"]], columns=["name", "jenjang", "city"])
    master, added = schools.build_master(portal, seen, pd.DataFrame(columns=["alias", "npsn"]), {})
    assert "SD Negeri 1" not in set(master["canonical_name"])  # it would match every SD Negeri 1
    assert {r["seen_name"]: r["result"] for _, r in added.iterrows()} == {"SDN 1": "not added, the name has no place", "SMA Islam Serang": "added with region other"}


def test_an_alias_that_differs_from_the_canonical_name_matches():
    master = MASTER.assign(aliases=["Pacet Satu", "", ""])
    found, _ = schools.lookup("Pacet Satu", master)
    assert found["npsn"] == "20200001"


def test_a_name_ending_in_a_city_is_also_narrowed_by_the_typed_city():
    none, suggestions = schools.lookup("SDN 1 Bandung", SHARED, city="Kabupaten Bandung")  # the end of the name allows both, the typed city picks one
    assert none is None or none["npsn"] == "30000002"
    found, _ = schools.lookup("SDN 1 Bandung", SHARED, city="Kabupaten Bandung")
    assert found is not None and found["npsn"] == "30000002"


def test_a_school_outside_the_four_regions_gets_the_typed_city_read_like_an_unknown_school():
    table, review = schools.canonicalize(students(["SMA Islam Serang", "Bandung"], ["SMA Islam Serang", "Kab. Bandung Barat"]), MASTER)
    assert list(table["Kota/Kabupaten"]) == ["Bandung", "Kabupaten Bandung Barat"]
    assert [(r["check"], r["value"], r["suggestions"]) for _, r in review.iterrows()] == [("region_ambiguous", "Bandung", "Kota Bandung | Kabupaten Bandung")]


@pytest.mark.parametrize(
    "typed, expected",
    [
        ("KBB", ("Kabupaten Bandung Barat",)),
        ("Kab. Bdg", ("Kabupaten Bandung",)),
        ("Kota Bdg", ("Kota Bandung",)),
        ("Kota Bandung Barat", ("Kabupaten Bandung Barat",)),  # Bandung Barat is a Kabupaten
        ("Bandungan", ()),
        ("Kabupaten Bandung, Jawa Barat", ("Kabupaten Bandung",)),
    ],
)
def test_typed_city_variants(typed, expected):
    assert schools.regions_of(typed) == expected


def test_the_state_prefix_may_be_followed_by_a_hyphen():
    assert schools.canonical("SMPN-1 Pacet") == "SMP Negeri 1 Pacet"


def test_more_typed_city_forms():
    assert schools.regions_of("Kab. Bandung Brt") == ("Kabupaten Bandung Barat",)
    assert schools.regions_of("Kota/Kabupaten Bandung") == ("Kota Bandung", "Kabupaten Bandung")  # both words: nothing is chosen

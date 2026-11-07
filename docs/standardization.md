# Standardization rules

What the `standardize` stage does to each field, and what it reports instead of guessing. Codes are the `code` column of the review report. Accepted values per column are in [input-template.md](input-template.md); their spellings are in `configs/default.yaml`.

Rule of thumb: fix what is certain (case, spacing, spelling variants from a list), report what is not.

## Names

| Field | Rule |
|---|---|
| Student name (`Nama Lengkap`) | Spaces collapsed, stray characters removed (`name_chars`), text in brackets removed (`name_brackets`), academic degrees at the end and `Dr`, `Drs`, `Dra`, `Ir`, `Prof` at the start removed (`name_title_removed`) |
| Case | A name in all capitals or all lower case becomes normal case (apostrophes and hyphens respected, roman numerals such as `III` kept). A name with mixed case is left as typed |
| Accompanying person (`Nama Pendamping`) | Same cleaning, degrees kept |
| Reported, not changed | Digits in a name (`name_digits`), a single-word student name (`name_single_word`), an empty name after cleaning (`missing_name`, an error for a student) |

Degrees are removed only when they match a list (`S.Pd`, `S.Kom`, `M.Pd`, ...) with the dot after S or M, so an initial such as `M. Ali` stays. Excel's escape for an invisible character (`_x0000_`) is removed.

## Contact fields

| Field | Rule |
|---|---|
| Phone | Digits only, `08...` form (`+62`, `62` and a lost leading 0 are repaired). With several numbers the first is kept (`phone_multiple`). A length outside 9 to 14 digits is reported (`phone_length`) |
| Email | Lower case, spaces and trailing punctuation removed, first address kept when there are several (`email_multiple`). An address that is not valid is reported (`invalid_email`): it must match the valid email address of the HTML Standard (section 4.10.5.1.5), be at most 254 characters with a local part of at most 64 (RFC 5321 section 4.5.3.1), and have a dot in the domain; a likely domain typo such as `gmial.com` is reported (`email_domain_typo`) |

## Identifiers

| Field | Rule |
|---|---|
| NISN | Exactly 10 digits, kept as text. Nine digits get a leading zero (`nisn_padded`, a warning). Anything else that is not a bureau code `<code>_NNNNN` is an error (`nisn_format`). Empty is an error (`missing_nisn`) |

## Values from a list

Gender, Kategori, Jenjang Sekolah, Status Pendamping, Bahasa and Nama Biro are matched case-insensitively against the spellings in the configuration. A value that matches none is an error and is kept as typed (`unknown_value`). Spellings seen in earlier workbooks are added to the configuration as they appear. A file that names another bureau gets `unknown_value` on `Nama Biro`.

| Field | Rule |
|---|---|
| Kelas | A number from 0 to 12; `7A`, `VIII`, `7.0` are read as 7, 8, 7. Anything else is an error (`kelas_invalid`) |
| Kategori | Must match Kelas: 0 to 3 SiKecil, 4 to 6 Siaga, 7 to 9 Penggalang, 10 to 12 Penegak (`kategori_mismatch`). An empty Kategori is filled from Kelas with a warning (`kategori_filled`) |
| Sesi | Upper case. Must be A to I or A1 to I1 (`sesi_invalid`) and must be available for the category: SiKecil has no E, letters with 1 are Penggalang only (`sesi_category`). Empty is a warning (`sesi_missing`) |

## Free text

School name: spaces collapsed, otherwise as typed; the canonical name and the region come from the school master in the `dedup` stage (see [pipeline.md](pipeline.md)). City: normal case when all capitals or all lower case; a name that matches no school or region is reported by the modules that know them.

## Template example rows

The template ships with two invented students. They are dropped when left in (`template_example`, a warning).

## Empty values

An empty required value is an error (name, school, NISN, Kelas). An empty optional value is a warning (`missing_value`) and is written as `-` in the standardized table.

## Columns shifted by a sender

A value that belongs in another column (a time in Kategori, a bureau name in Sesi, a phone number in Status Pendamping) fails the list check of the column it landed in and is reported as an error. Such a row is clarified with the sender; it is not moved automatically.

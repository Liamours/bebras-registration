from registration.replies import build_reply
from registration.review import Issue


def issue(row, col, code, severity="error", value=""):
    return Issue("f.xlsx", row, col, value, "reason", severity, code)


def test_errors_are_grouped_by_problem_with_row_numbers(replies):
    text = build_reply(replies, [issue(3, "NISN", "missing_nisn"), issue(5, "NISN", "missing_nisn"), issue(4, "Gender", "unknown_value", value="x")], school="SMP Contoh")
    assert "dari SMP Contoh" in text
    assert "NISN belum diisi, baris 3, 5." in text
    assert "kolom Gender" in text and "baris 4 ('x')" in text
    assert text.strip().endswith("Terima kasih.")


def test_warnings_alone_give_no_reply(replies):
    assert build_reply(replies, [issue(2, "NISN", "nisn_padded", "warning")]) is None
    assert build_reply(replies, []) is None


def test_every_error_code_the_stages_can_raise_has_a_message(replies):
    errors = {"missing_name", "missing_school", "missing_nisn", "nisn_format", "unknown_value", "kelas_invalid",
              "kategori_mismatch", "sesi_invalid", "sesi_category", "missing_column", "invalid_email"}
    rejects = {"reject_unreadable", "reject_no_table", "reject_no_rows", "reject_missing_column", "reject_old_template"}
    assert (errors | rejects) <= set(replies["codes"])


def test_rejected_file_message_names_the_missing_columns(replies):
    text = build_reply(replies, [], rejected=[("reject_missing_column", "Nama Sekolah")])
    assert "belum dapat kami proses" in text and "Nama Sekolah" in text


def test_every_reply_code_is_documented(replies):
    from pathlib import Path
    page = Path(__file__).resolve().parents[1].joinpath("docs", "reply-templates.md").read_text(encoding="utf-8")
    assert all(f"`{code}`" in page for code in replies["codes"])

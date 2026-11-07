import pytest

from registration import school_source

PAGE = """DAFTAR SATUAN PENDIDIKAN
<tr><td align="right">1</td><td class="link1"><a target="_blank"
 href="https://example.org/pendidikan/npsn/20200001">20200001</a></td>
 <td>SMP NEGERI 1 PACET</td><td>Jl. Contoh No. 1</td><td>Pacet</td><td>NEGERI</td></tr>
<tr><td align="right">2</td><td class="link1"><a href="https://example.org/pendidikan/npsn/20200002">20200002</a></td>
 <td>SD &amp; MI Contoh</td><td>Jl. Lain</td><td>Cipanas</td><td>SWASTA</td></tr>"""


def test_rows_of_a_school_page_are_read_with_html_entities_decoded():
    assert school_source.parse_rows(PAGE) == [["20200001", "SMP NEGERI 1 PACET", "Jl. Contoh No. 1", "Pacet", "NEGERI"], ["20200002", "SD & MI Contoh", "Jl. Lain", "Cipanas", "SWASTA"]]


def test_a_page_without_the_school_table_stops_the_download_and_is_not_marked_done(tmp_path, monkeypatch):
    cfg = {"school_source": {"base": "https://example.org/p", "delay_seconds": 0, "regions": {"Kota Bandung": "026000"}, "forms": {"dikdas": {"SD": 5}}}}

    def fake_get(url, tries=4):
        return '<a href="/dikdas/026001/3">Kec A</a>' if url.endswith("/2") else "<html>error page</html>"

    monkeypatch.setattr(school_source, "get", fake_get)
    state = tmp_path / "done.txt"
    with pytest.raises(RuntimeError):
        school_source.build(cfg, tmp_path / "out.csv", state, lambda *_: None)
    assert not state.read_text(encoding="utf-8").strip()


def test_a_download_marks_a_page_done_and_a_rerun_skips_it(tmp_path, monkeypatch):
    cfg = {"school_source": {"base": "https://example.org/p", "delay_seconds": 0, "regions": {"Kota Bandung": "026000"}, "forms": {"dikdas": {"SD": 5}}}}
    calls = []

    def fake_get(url, tries=4):
        calls.append(url)
        return '<a href="/dikdas/026001/3">Kec A</a>' if url.endswith("/2") else PAGE

    monkeypatch.setattr(school_source, "get", fake_get)
    out, state = tmp_path / "out.csv", tmp_path / "done.txt"
    assert school_source.build(cfg, out, state, lambda *_: None) == 2
    assert school_source.build(cfg, out, state, lambda *_: None) == 0 and len(out.read_text(encoding="utf-8").splitlines()) == 3

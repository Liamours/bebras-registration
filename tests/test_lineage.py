import pandas as pd

from registration.lineage import lineage
from registration.partition import partition
from registration.status import mark_uploaded
from tests.test_audit import export, prepare


def test_each_hop_of_a_value_is_named(make_workbook, cfg, replies, row):
    cfg["paths"]["overrides"].write_text("source_file,row,column,new_value,reason,student\na.xlsx,2,Sesi,C,class moved,ANI SATU\n", encoding="utf-8")
    std = prepare(make_workbook, cfg, replies, row, rows=[row(**{"Nama Lengkap": "ANI SATU", "NISN": 3000000001, "Sesi": "b"}), row(**{"Nama Lengkap": "Budi Dua", "NISN": 3000000002})])
    file = partition(cfg, stamp="20261105-1000").iloc[0]["file"]
    mark_uploaded(cfg["paths"]["submit_ready"], file)
    site = export(cfg, std, change=(1, "Nama Lengkap", "Budi Duaa"))
    table = lineage(cfg, site)
    ani = table[table["source_row"] == 2].set_index("field")
    assert ani.loc["Sesi", "raw"] == "b" and ani.loc["Sesi", "final"] == "C" and ani.loc["Sesi", "raw_to_final"].startswith("override: class moved")
    assert ani.loc["Nama Lengkap", "raw"] == "ANI SATU" and ani.loc["Nama Lengkap", "final"] == "Ani Satu" and ani.loc["Nama Lengkap", "raw_to_final"] == "rule: format"
    assert ani.loc["Sesi", "uploaded_in"].startswith(file)
    budi = table[table["source_row"] == 3].set_index("field")  # the site holds another spelling than the file: no match by name, so no site columns
    assert budi.loc["Gender", "raw_to_final"].startswith("rule")

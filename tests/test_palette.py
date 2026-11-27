from sqlch_gui import palette


def _write(tmp_path, body):
    f = tmp_path / "palette.sh"
    f.write_text(body)
    return str(f)


def test_load_new_names(tmp_path):
    p = palette.load(_write(tmp_path, 'export LIGHT="#ffffff"\nexport SUN="#123456"\n'))
    assert p["LIGHT"] == "#ffffff" and p["SUN"] == "#123456"


def test_load_translates_old_names(tmp_path):
    p = palette.load(_write(tmp_path, 'export SCORE="#ffffff"\nexport STAFF_A_DROP="0.9"\n'))
    assert p["LIGHT"] == "#ffffff" and p["UMBRA_A_DROP"] == "0.9"
    assert "SCORE" not in p


def test_defaults_use_new_names(tmp_path):
    p = palette.load(str(tmp_path / "missing.sh"))
    assert {"NIGHT", "LIGHT", "SUN", "UMBRA_RGB", "GRAD_NIGHT_HI"} <= set(p)
    assert not ({"HALL", "SCORE", "ROOT", "STAFF"} & set(p))

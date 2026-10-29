"""Public template import/export: strict schema, no secrets, no side effects."""
import json
import subprocess
import webbrowser

import pytest

from misong import templates as tpl
from misong.desktop.api import DEFAULT_TEMPLATES, MAX_TEMPLATES
from misong.templates import TemplateError

PASSWORD = "Synth-Layer-Pass-77"
VIDEO = "C:\\Users\\synthuserqq\\cover.mp4"
MOJI_KEY = "SynthMagicKey42"
RECIPE = {"version": 1, "id": "r1", "name": "魔曰链", "layers": [
    {"id": "l1", "scheme": "base64", "version": 1, "params": {}, "secret_slot": None},
    {"id": "l2", "scheme": "mojibake", "version": 1, "params": {"mode": "wenyan"}, "secret_slot": "r1/l2"}],
    "carrier": {"format_id": "text", "version": 1, "mode": "plain", "params": {}, "secret_slot": None}}
STORED = {"name": "我的模板", "created": "2026-10-29T10:00:00", "disguise": ".mp4", "size": "1900M",
          "layers": [{"fmt": "lz4", "locked": True, "header_enc": True, "password": PASSWORD},
                     {"fmt": "7z", "locked": True, "header_enc": True, "level": 5},
                     {"type": "cover", "video": VIDEO}, {"type": "split", "size": "1G"}],
          "options": {"raw_merge": True, "checksum": False}, "text_recipes": [RECIPE]}


def _doc(**template):
    item = {"name": "t", "layers": [{"fmt": "7z", "locked": True, "header_enc": True}], **template}
    return {"schema_version": 1, "kind": "misong-templates", "templates": [item]}


def test_export_contains_only_public_fields(tmp_path):
    out = tmp_path / "t.json"
    tpl.export_file([STORED, *DEFAULT_TEMPLATES], out)
    text = out.read_text(encoding="utf-8")
    for secret in (PASSWORD, VIDEO, "synthuserqq", MOJI_KEY, "password", "created", "export_key"):
        assert secret not in text
    doc = json.loads(text)
    assert doc["schema_version"] == 1 and doc["kind"] == "misong-templates"
    first = doc["templates"][0]
    assert first["layers"][0] == {"fmt": "lz4", "locked": False, "header_enc": True}  # lz4 has no password
    assert first["layers"][1]["level"] == 5 and first["layers"][2] == {"type": "cover", "video": ""}
    assert first["options"] == {"raw_merge": True, "checksum": False}
    assert first["text_recipes"] == [RECIPE]
    assert len(doc["templates"]) == 1 + len(DEFAULT_TEMPLATES)


def test_round_trip_and_conflict_renaming(tmp_path):
    out = tmp_path / "t.json"
    tpl.export_file([STORED, *DEFAULT_TEMPLATES], out)
    long_name = "一" * 24
    existing = [{"name": "我的模板", "layers": []}, {"name": "我的模板 (2)", "layers": []},
                {"name": DEFAULT_TEMPLATES[0]["name"].upper(), "layers": []}]
    result = tpl.import_file(out, existing)
    names = [t["name"] for t in result["templates"]]
    assert len(names) == len({n.casefold() for n in names}) == 3 + 1 + len(DEFAULT_TEMPLATES)
    assert {"from": "我的模板", "to": "我的模板 (3)"} in result["renamed"]
    imported = result["templates"][3]
    assert imported["text_recipes"] == [RECIPE] and imported["created"]
    assert tpl.unique_name(long_name, [long_name]) == "一" * 20 + " (2)"
    assert len(tpl.unique_name(long_name, [long_name])) == 24
    again = tpl.parse_document(json.dumps(tpl.export_document(result["templates"][3:])))
    assert again[0]["layers"] == imported["layers"]


@pytest.mark.parametrize("doc", [
    {"schema_version": 2, "kind": "misong-templates", "templates": []},
    {"schema_version": True, "kind": "misong-templates", "templates": [{}]},
    {"schema_version": "1", "kind": "misong-templates", "templates": [{}]},
    {"kind": "misong-templates", "templates": [{}]},
    {"schema_version": 1, "kind": "other", "templates": [{}]},
    {**_doc(), "extra": 1},
    {"schema_version": 1, "kind": "misong-templates", "templates": {}},
    {"schema_version": 1, "kind": "misong-templates", "templates": []},
    [1, 2],
    _doc(account="me"),
    _doc(password=PASSWORD),
    _doc(inputs=["C:/x"]),
    _doc(session={}),
    _doc(export_keys=["r1"]),
    _doc(created="x"),
    _doc(name=""),
    _doc(name="x" * 25),
    _doc(name="a\nb"),
    _doc(name=3),
    _doc(layers=[]),
    _doc(layers="7z"),
    _doc(layers=[{"fmt": "7z", "locked": True, "header_enc": True, "password": PASSWORD}]),
    _doc(layers=[{"fmt": "7z", "locked": "yes", "header_enc": True}]),
    _doc(layers=[{"fmt": "nope", "locked": False, "header_enc": True}]),
    _doc(layers=[{"fmt": "7z", "locked": False, "header_enc": True, "level": 99}]),
    _doc(layers=[{"fmt": "7z", "locked": True, "header_enc": True}, {"type": "cover", "video": VIDEO}]),
    _doc(layers=[{"type": "run", "cmd": "calc"}]),
    _doc(layers=[{"fmt": "7z", "locked": True, "header_enc": True}, {"type": "rename", "ext": "../x"}]),
    _doc(layers=[{"fmt": "7z", "locked": True, "header_enc": True}] * 33),
    _doc(disguise=".exe"),
    _doc(size="lots"),
    _doc(options={"raw_merge": 1}),
    _doc(options={"open_url": True}),
    _doc(text_recipes=[{**RECIPE, "export_key": True}]),
    _doc(text_recipes=[{**RECIPE, "secrets": {"r1/l2": MOJI_KEY}}]),
    _doc(text_recipes=[{**RECIPE, "layers": [{**RECIPE["layers"][1], "key": MOJI_KEY}]}]),
    _doc(text_recipes=[{**RECIPE, "source_text": "hello"}]),
    _doc(text_recipes=[RECIPE] * 17),
    _doc(text_recipes=[RECIPE, RECIPE]),
])
def test_rejects_bad_documents(doc):
    with pytest.raises(TemplateError):
        tpl.parse_document(json.dumps(doc))


def test_rejects_raw_format_problems(tmp_path):
    good = json.dumps(_doc())
    for text in ("{not json", good.replace('"kind"', '"kind": "x", "kind"'),
                 '{"schema_version": NaN, "kind": "misong-templates", "templates": []}',
                 "[" * 100000, b"\xff\xfe", b" " * (tpl.MAX_FILE_BYTES + 1)):
        with pytest.raises(TemplateError):
            tpl.parse_document(text)
    many = {"schema_version": 1, "kind": "misong-templates",
            "templates": [_doc(name=f"t{i}")["templates"][0] for i in range(MAX_TEMPLATES + 1)]}
    with pytest.raises(TemplateError):
        tpl.parse_document(json.dumps(many))
    big = tmp_path / "big.json"
    big.write_bytes(b" " * (tpl.MAX_FILE_BYTES + 1))
    for path in (big, tmp_path / "missing.json", tmp_path, tmp_path / "x.txt"):
        with pytest.raises(TemplateError):
            tpl.read_file(path)


def test_import_capacity_and_overwrite(tmp_path):
    out = tmp_path / "t.json"
    tpl.export_file([STORED], out)
    before = out.read_bytes()
    with pytest.raises(TemplateError):
        tpl.export_file([STORED], out)
    assert out.read_bytes() == before
    with pytest.raises(TemplateError):
        tpl.export_file([STORED], tmp_path / "t.txt")
    with pytest.raises(TemplateError):
        tpl.export_file([], tmp_path / "e.json")
    full = [{"name": f"x{i}", "layers": []} for i in range(MAX_TEMPLATES)]
    with pytest.raises(TemplateError):
        tpl.import_file(out, full)


def test_symlinked_template_file_rejected(tmp_path):
    real = tmp_path / "real.json"
    real.write_text(json.dumps(_doc()), encoding="utf-8")
    link = tmp_path / "link.json"
    try:
        link.symlink_to(real)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    with pytest.raises(TemplateError):
        tpl.read_file(link)


def test_import_has_no_side_effects(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("side effect")
    monkeypatch.setattr(subprocess, "Popen", boom)
    monkeypatch.setattr(subprocess, "run", boom)
    monkeypatch.setattr(webbrowser, "open", boom)
    import os
    if hasattr(os, "startfile"):
        monkeypatch.setattr(os, "startfile", boom)
    monkeypatch.setattr(os, "system", boom)
    path = tmp_path / "t.json"
    doc = _doc(name="https://example.com/run", disguise=".mp4",
               layers=[{"fmt": "7z", "locked": True, "header_enc": True},
                       {"type": "rename", "ext": "bat"}])
    path.write_text(json.dumps(doc), encoding="utf-8")
    before = sorted(p.name for p in tmp_path.iterdir())
    result = tpl.import_file(path, [])
    assert result["added"] == ["https://example.com/run"]
    assert sorted(p.name for p in tmp_path.iterdir()) == before

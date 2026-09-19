"""`flask make-sample-scans`(체험 예시 사진 만들기, 스펙 31절). 실제 AI 대신 가짜 extract, 사진·결과 파일은 임시 폴더."""

import io
import json
from types import SimpleNamespace

import pytest
from PIL import Image

from app import ai, scan

OLD_ERECEIPT = {
    "kind": "receipt",
    "items": [{"name": "애호박", "quantity": 1.0, "unit": "개", "location_kind": "fridge", "price": 1580}],
    "purchased_on": "2026-08-18",
}


def photo_bytes(fmt="JPEG"):
    """긴 변이 1568px보다 크고 사진 정보(EXIF)가 든 작은 사진"""
    exif = Image.Exif()
    exif[0x010F] = "TestMaker"  # Make
    exif[0x0110] = "TestPhone"  # Model
    buffer = io.BytesIO()
    Image.new("RGB", (2000, 1000), (200, 180, 160)).save(buffer, fmt, exif=exif)
    return buffer.getvalue()


@pytest.fixture
def cli(make_app, tmp_path, monkeypatch):
    photos = tmp_path / "photos"
    photos.mkdir()
    scans_file = tmp_path / "sample_scans.json"
    scans_file.write_text(json.dumps({"ereceipt": OLD_ERECEIPT}, ensure_ascii=False), encoding="utf-8")
    out = tmp_path / "samples"
    monkeypatch.setattr(ai, "SAMPLE_SCANS_FILE", scans_file)
    monkeypatch.setattr(scan, "SAMPLE_PHOTO_DIR", out)
    calls, failing = [], set()

    def fake_extract(kind, images, locations=()):
        calls.append(kind)
        assert [mime for _, mime in images] == ["image/jpeg"]
        if kind in failing:
            raise ai.AiError("거절")
        items = [{"name": f"{kind} 재료", "quantity": 1, "unit": "개", "location_kind": "fridge", "price": None}]
        return {"items": items, "purchased_on": None}, {"model": "m", "input_tokens": 3, "output_tokens": 4}

    monkeypatch.setattr(ai, "extract", fake_extract)
    app = make_app(ANTHROPIC_API_KEY="test-key")

    def run(*ids):
        return app.test_cli_runner().invoke(args=["make-sample-scans", str(photos), *ids])

    return SimpleNamespace(run=run, photos=photos, out=out, calls=calls, failing=failing,
                           stored=lambda: json.loads(scans_file.read_text(encoding="utf-8")))


def test_unknown_id_stops_before_ai(cli):
    result = cli.run("order")
    assert result.exit_code != 0
    assert "모르는 사진 id: order" in result.output
    assert cli.calls == []


def test_rerun_one_photo_keeps_other_results_and_strips_photo_info(cli):
    (cli.photos / "fridge.jpg").write_bytes(photo_bytes())
    result = cli.run("fridge")
    assert result.exit_code == 0, result.output
    assert cli.calls == ["fridge"]
    stored = cli.stored()
    assert stored["ereceipt"] == OLD_ERECEIPT  # 다시 만들지 않은 사진의 결과는 그대로
    assert stored["fridge"] == {
        "kind": "fridge",
        "items": [{"name": "fridge 재료", "quantity": 1.0, "unit": "개", "location_kind": "fridge", "price": None}],
        "purchased_on": None,
    }
    with Image.open(cli.out / "fridge.jpg") as image:
        assert image.format == "JPEG"
        assert image.size == (1568, 784)  # 긴 변 1568px로 줄였다
        assert not image.getexif() and "exif" not in image.info  # 사진 정보는 따라가지 않는다


def test_later_failure_keeps_earlier_photo_and_result(cli):
    (cli.photos / "ereceipt.png").write_bytes(photo_bytes("PNG"))
    (cli.photos / "fridge.jpg").write_bytes(photo_bytes())
    cli.failing.add("fridge")
    result = cli.run("ereceipt", "fridge")
    assert result.exit_code != 0
    assert "fridge 사진을 읽지 못했어요(거절)" in result.output
    assert cli.calls == ["receipt", "fridge"]
    stored = cli.stored()
    assert [i["name"] for i in stored["ereceipt"]["items"]] == ["receipt 재료"]  # 앞 사진의 새 결과는 이미 저장됐다
    assert "fridge" not in stored
    assert (cli.out / "ereceipt.jpg").is_file()
    assert not (cli.out / "fridge.jpg").exists()  # 못 읽은 사진은 쓰지 않는다


def test_unreadable_photo_names_the_file(cli):
    (cli.photos / "fridge.jpg").write_bytes(b"not a photo")
    result = cli.run("fridge")
    assert result.exit_code != 0
    assert "fridge.jpg 파일을 사진으로 열지 못했어요" in result.output
    assert cli.calls == []
    assert cli.stored() == {"ereceipt": OLD_ERECEIPT}

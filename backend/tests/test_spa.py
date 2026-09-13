def test_serves_spa_and_assets(make_app, tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<div id=root></div>")
    (tmp_path / "assets" / "app.js").write_text("console.log(1)")
    c = make_app(FRONTEND_DIST=str(tmp_path)).test_client()

    assert b"root" in c.get("/").data
    assert b"root" in c.get("/some/client/route").data
    assert c.get("/assets/app.js").data == b"console.log(1)"

    res = c.get("/api/nope")
    assert res.status_code == 404
    assert res.get_json() == {"error": "찾을 수 없어요."}

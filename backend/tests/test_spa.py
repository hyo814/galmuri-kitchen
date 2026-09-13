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


def test_unknown_api_path_is_404_for_all_methods(make_app, tmp_path):
    (tmp_path / "index.html").write_text("<div id=root></div>")
    c = make_app(FRONTEND_DIST=str(tmp_path)).test_client()
    c.environ_base["HTTP_X_REQUESTED_WITH"] = "fetch"

    for res in (c.post("/api/nope"), c.delete("/api/nope")):
        assert res.status_code == 404
        assert res.get_json() == {"error": "찾을 수 없어요."}

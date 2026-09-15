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


def test_sw_and_manifest_served_with_no_cache_headers(make_app, tmp_path):
    (tmp_path / "index.html").write_text("<div id=root></div>")
    (tmp_path / "sw.js").write_text("self.addEventListener('install', () => {});")
    (tmp_path / "manifest.webmanifest").write_text('{"name": "test"}')
    c = make_app(FRONTEND_DIST=str(tmp_path)).test_client()

    sw = c.get("/sw.js")
    assert sw.headers["Cache-Control"] == "no-cache"
    assert sw.mimetype == "text/javascript"

    manifest = c.get("/manifest.webmanifest")
    assert manifest.headers["Cache-Control"] == "no-cache"
    assert manifest.mimetype == "application/manifest+json"


def test_hashed_assets_cached_long_but_index_is_not(make_app, tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<div id=root></div>")
    (tmp_path / "assets" / "index-abc.js").write_text("console.log(1)")
    (tmp_path / "icon-192.png").write_bytes(b"png")
    c = make_app(FRONTEND_DIST=str(tmp_path)).test_client()

    assert c.get("/assets/index-abc.js").headers["Cache-Control"] == "public, max-age=31536000, immutable"
    for path in ("/", "/some/client/route", "/icon-192.png"):
        assert "immutable" not in c.get(path).headers.get("Cache-Control", "")

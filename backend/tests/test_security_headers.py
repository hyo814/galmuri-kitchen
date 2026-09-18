"""모든 응답에 붙는 공통 보안 헤더(app/__init__.py의 security_headers).

운영 점검(2026-09-19)에서 여섯 종이 전부 없는 것을 확인해 넣었다. 개별 응답이 이미 정한 헤더는
덮지 않아야 한다 — 사진은 더 센 CSP(`default-src 'none'; sandbox`), 쿠팡 이동은 `no-referrer`를 쓴다.
"""

COMMON = ("X-Content-Type-Options", "X-Frame-Options", "Content-Security-Policy", "Referrer-Policy", "Permissions-Policy")


def test_common_headers_on_every_response(raw_client):
    """로그인 전에도, 404에도 붙는다(오류 응답으로 헤더가 빠지면 뜻이 없다)."""
    for path in ("/api/auth-options", "/api/me", "/api/nope"):
        res = raw_client.get(path)
        for name in COMMON:
            assert res.headers.get(name), f"{path} 응답에 {name}가 없어요"
        assert res.headers["X-Frame-Options"] == "DENY"
        assert "frame-ancestors 'none'" in res.headers["Content-Security-Policy"]


def test_hsts_only_outside_dev(raw_client, make_app):
    """개발은 http라 HSTS를 걸면 브라우저가 기억해 버린다. 운영에서만 붙인다."""
    assert "Strict-Transport-Security" not in raw_client.get("/api/auth-options").headers

    prod = make_app(DEV_MODE=False)
    res = prod.test_client().get("/api/auth-options")
    assert res.headers["Strict-Transport-Security"].startswith("max-age=")


def test_does_not_override_stricter_per_response_headers(client, login, app):
    """내보내기는 스스로 nosniff를 정한다 — setdefault라 그대로 남는다."""
    login()
    res = client.get("/api/export/summary")
    assert res.status_code == 200
    assert res.headers["X-Content-Type-Options"] == "nosniff"

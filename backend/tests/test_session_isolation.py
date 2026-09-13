"""Regression test for a fresh DB session per request.

Guards against the `app` fixture holding one app context (and therefore one
Flask-SQLAlchemy session) open across every test-client request: a route that
`db.session.add()`s without `commit()` must not leak into a later request.
"""

from app.models import User, db


def test_uncommitted_add_not_visible_to_next_request(app):
    @app.post("/api/_test/uncommitted")
    def _add_uncommitted():
        db.session.add(User(provider="test", provider_id="ghost", nickname="ghost"))
        return "", 204

    @app.get("/api/_test/count")
    def _count():
        return {"count": User.query.filter_by(provider_id="ghost").count()}

    client = app.test_client()
    client.environ_base["HTTP_X_REQUESTED_WITH"] = "fetch"

    assert client.post("/api/_test/uncommitted").status_code == 204
    # A later, separate request must get its own session and must NOT see the
    # uncommitted row (it would if the app fixture reused one session/context
    # across requests, since autoflush would flush the pending insert).
    assert client.get("/api/_test/count").get_json()["count"] == 0

import pytest

DEFAULTS = {
    "달걀": (25, 30, "user"),
    "계란": (25, 30, "user"),
    "두부": (15, 18, "mfds"),
    "요거트": (22, 25, "mfds"),
    "요구르트": (22, 25, "mfds"),
    "주스": (25, 28, "mfds"),
    "빵": (21, 24, "mfds"),
    "어묵": (30, 33, "mfds"),
    "소시지": (41, 44, "mfds"),
    "햄": (42, 45, "mfds"),
}


def rules_by_keyword(client):
    return {r["keyword"]: r for r in client.get("/api/item-rules").get_json()}


def test_new_user_gets_default_rules(client, login):
    login()
    rules = rules_by_keyword(client)
    assert {k: (r["warn_days"], r["danger_days"], r["source"]) for k, r in rules.items()} == DEFAULTS
    assert "우유" not in rules


def test_dev_login_seeds_rules_once(client):
    client.post("/api/dev-login")
    client.post("/api/dev-login")
    assert len(client.get("/api/item-rules").get_json()) == len(DEFAULTS)


def test_create_update_delete(client, login):
    login()
    res = client.post("/api/item-rules", json={"keyword": "닭가슴살", "warn_days": 2, "danger_days": 4})
    assert res.status_code == 201
    assert res.get_json()["source"] == "user"

    tofu = rules_by_keyword(client)["두부"]
    res = client.patch(f"/api/item-rules/{tofu['id']}", json={"danger_days": 20})
    assert res.status_code == 200
    body = res.get_json()
    assert (body["warn_days"], body["danger_days"], body["source"]) == (15, 20, "user")

    assert client.delete(f"/api/item-rules/{tofu['id']}").status_code == 204
    assert "두부" not in rules_by_keyword(client)


@pytest.mark.parametrize(
    "body",
    [
        {"keyword": "", "warn_days": 1, "danger_days": 2},
        {"keyword": "닭", "warn_days": 0, "danger_days": 2},
        {"keyword": "닭", "warn_days": 3, "danger_days": 3},
        {"keyword": "닭", "warn_days": True, "danger_days": 3},
        {"keyword": "닭", "warn_days": "2", "danger_days": 3},
        {"keyword": "두부", "warn_days": 1, "danger_days": 2},
    ],
)
def test_create_validation(client, login, body):
    login()
    res = client.post("/api/item-rules", json=body)
    assert res.status_code == 400
    assert "error" in res.get_json()


def test_patch_must_keep_red_after_yellow(client, login):
    login()
    egg = rules_by_keyword(client)["계란"]
    res = client.patch(f"/api/item-rules/{egg['id']}", json={"warn_days": 30})
    assert res.status_code == 400
    assert res.get_json()["error"] == "빨강 경고 일수는 노랑보다 커야 해요."


def test_other_users_rule_is_hidden(client, login):
    login("owner")
    rule_id = rules_by_keyword(client)["햄"]["id"]
    login("intruder")
    assert client.patch(f"/api/item-rules/{rule_id}", json={"warn_days": 1}).status_code == 404
    assert client.delete(f"/api/item-rules/{rule_id}").status_code == 404


# 마이그레이션 a3b3c3d3e3f3가 실행된 시점의 기본 규칙을 그대로 고정한 값.
# 이후 app.defaults.DEFAULT_RULES를 바꾸더라도 이미 배포된 마이그레이션은 절대 수정하지 않는다 —
# 기본값을 바꾸려면 새 마이그레이션을 추가한다.
FROZEN_MIGRATION_DEFAULTS = [
    ("달걀", 25, 30, "user"),
    ("계란", 25, 30, "user"),
    ("두부", 15, 18, "mfds"),
    ("요거트", 22, 25, "mfds"),
    ("요구르트", 22, 25, "mfds"),
    ("주스", 25, 28, "mfds"),
    ("빵", 21, 24, "mfds"),
    ("어묵", 30, 33, "mfds"),
    ("소시지", 41, 44, "mfds"),
    ("햄", 42, 45, "mfds"),
]


def test_migration_defaults_match_app_defaults():
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "migrations" / "versions" / "a3b3c3d3e3f3_item_rules.py"
    spec = importlib.util.spec_from_file_location("item_rules_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    assert migration.DEFAULT_RULES == FROZEN_MIGRATION_DEFAULTS


def test_app_defaults_match_frozen_defaults_today():
    # 오늘 기준으로 app.defaults.DEFAULT_RULES가 마이그레이션 시점 값과 같은지 확인.
    # 앞으로 기본값을 바꾸면 이 테스트가 실패한다 — 그때는 위 마이그레이션 상수를 고치는 게 아니라
    # 새 마이그레이션을 추가하고, 이 테스트의 기대값만 최신 app.defaults로 갱신한다.
    from app.defaults import DEFAULT_RULES

    assert DEFAULT_RULES == FROZEN_MIGRATION_DEFAULTS

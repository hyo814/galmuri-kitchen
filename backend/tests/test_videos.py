from datetime import timedelta, timezone

import pytest

from app import outbound, videos
from app.models import AiCall, User, UserChannel, YoutubeChannel, YoutubeVideo, db, utcnow
from app.outbound import FetchError


def cid(name):
    return f"UC{name:_<22}"


def vid(name):
    return f"{name:x<11}"


def fail_if_called(*args, **kwargs):
    raise AssertionError("유튜브를 부르면 안 돼요")


@pytest.fixture
def on_app(make_app):
    return make_app(YOUTUBE_API_KEY="k")


@pytest.fixture
def on_client(on_app):
    c = on_app.test_client()
    c.environ_base["HTTP_X_REQUESTED_WITH"] = "fetch"
    return c


@pytest.fixture
def on_login(on_client, on_app):
    def _login(provider_id="1"):
        with on_app.app_context():
            user = User(provider="test", provider_id=provider_id, nickname="u")
            db.session.add(user)
            db.session.commit()
            user_id = user.id
        with on_client.session_transaction() as s:
            s["user_id"], s["pid"] = user_id, provider_id
        return user_id

    return _login


@pytest.fixture
def no_youtube(monkeypatch):
    for name in ("channel_info", "playlist_videos", "video_details"):
        monkeypatch.setattr(outbound, name, fail_if_called)


def make_channel(app, name, *, default=False, fetched_ago=timedelta(0), videos_=(), user_rows=(), uploads=True):
    """videos_: [(이름, 며칠 전, 제목)], user_rows: [(user_id, hidden)]. 채널 pk를 돌려준다."""
    with app.app_context():
        now = utcnow()
        channel = YoutubeChannel(
            channel_id=cid(name),
            title=f"채널 {name}",
            is_default=default,
            uploads_playlist_id=f"UU{name}" if uploads else None,
            fetched_at=None if fetched_ago is None else now - fetched_ago,
        )
        db.session.add(channel)
        db.session.flush()
        for video_name, days, title in videos_:
            db.session.add(
                YoutubeVideo(
                    video_id=vid(video_name),
                    channel_id=channel.id,
                    title=title,
                    published_at=now - timedelta(days=days),
                    fetched_at=now,
                    duration_seconds=60,
                )
            )
        for user_id, hidden in user_rows:
            db.session.add(UserChannel(user_id=user_id, channel_id=channel.id, hidden=hidden))
        db.session.commit()
        return channel.id


@pytest.mark.parametrize(
    "value, expected",
    [
        ("https://www.youtube.com/channel/UCabcdefghijklmnopqrstuv", ("id", "UCabcdefghijklmnopqrstuv")),
        ("https://youtube.com/@cookhouse?si=abc", ("handle", "@cookhouse")),
        ("m.youtube.com/@cook.house/videos", ("handle", "@cook.house")),
        ("@cookhouse", ("handle", "@cookhouse")),
        ("https://www.youtube.com/@%EC%A7%91%EB%B0%A5%EC%97%B0%EA%B5%AC%EC%86%8C", ("handle", "@집밥연구소")),
        ("http://www.youtube.com/user/maangchi", ("username", "maangchi")),
        ("https://www.youtube.com/channel/UCabcdefghijklmnopqrstuv/videos", ("id", "UCabcdefghijklmnopqrstuv")),
        ("https://www.youtube.com/c/maangchi", None),  # 공식 조회 방법이 없다
        ("https://www.youtube.com/c/%EC%A7%91%EB%B0%A5%EC%97%B0%EA%B5%AC%EC%86%8C", None),
        ("https://evil.example/@cookhouse", None),
        ("https://www.youtube.com/channel/UCshort", None),
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", None),
        ("javascript:alert(1)", None),
        ("@ab", None),
        ("", None),
        (None, None),
        ("https://www.youtube.com/@" + "a" * 500, None),
    ],
)
def test_parse_channel_link(value, expected):
    assert videos.parse_channel_link(value) == expected


def test_videos_modes(client, login, app, no_youtube):
    login()
    res = client.get("/api/videos")
    body = res.get_json()
    assert res.status_code == 200 and body["sample"] is True and body["next_cursor"] is None
    assert [v["title"] for v in body["items"]][:2] == ["제육볶음 황금레시피, 이렇게만 하세요", "냉장고 털이 두부조림 10분 완성"]
    assert len(body["items"]) == 5 and all(v["thumbnail_url"] is None and len(v["video_id"]) == 11 for v in body["items"])
    assert body["items"][0]["duration_seconds"] == 724 and body["items"][0]["channel_title"] == "집밥 연구소"
    assert [v["id"] for v in client.get("/api/videos?q=두부").get_json()["items"]] == [2]
    assert [v["id"] for v in client.get("/api/videos?channel=2").get_json()["items"]] == [2, 5]
    assert client.get("/api/videos/1").get_json()["description"].startswith("재료 (3인분)")
    assert client.get("/api/videos/9").status_code == 404
    channels = client.get("/api/channels").get_json()
    assert (len(channels["items"]), channels["mine_count"], channels["mine_limit"], channels["sample"]) == (5, 2, 30, True)
    res = client.post("/api/channels", json={"url": "https://youtube.com/@cookhouse"})
    assert (res.status_code, res.get_json()["error"]) == (503, "지금은 채널을 추가할 수 없어요.")
    assert client.patch("/api/channels/3", json={"hidden": True}).status_code == 503
    assert client.delete("/api/channels/1").status_code == 503

    app.config.update(DEV_MODE=False)
    for path in ("/api/videos", "/api/videos/1", "/api/channels"):
        res = client.get(path)
        assert (res.status_code, res.get_json()["error"]) == (503, "영상을 지금은 볼 수 없어요.")
    with app.app_context():
        assert YoutubeChannel.query.count() == 0


def test_videos_lists_visible_channels_newest_first_with_cursor(on_client, on_login, on_app, no_youtube):
    me, other = on_login("2"), None
    with on_app.app_context():
        other_user = User(provider="test", provider_id="other", nickname="o")
        db.session.add(other_user)
        db.session.commit()
        other = other_user.id
    make_channel(on_app, "A", default=True, videos_=[("a1", 1, "A 하나"), ("a2", 3, "A 둘"), ("a3", 5, "A 셋")])
    make_channel(on_app, "B", default=True, videos_=[("b1", 0, "B 하나"), ("b2", 2, "B 둘")], user_rows=[(me, True)])
    make_channel(on_app, "C", videos_=[("c1", 2, "C 하나"), ("c2", 4, "C 둘")], user_rows=[(me, False)])
    make_channel(on_app, "D", videos_=[("d1", 1, "D 하나")], user_rows=[(other, False)])

    body = on_client.get("/api/videos").get_json()
    assert [v["title"] for v in body["items"]] == ["A 하나", "C 하나", "A 둘", "C 둘", "A 셋"]
    assert body["next_cursor"] is None and body["sample"] is False
    first = body["items"][0]
    assert set(first) == {"id", "video_id", "title", "thumbnail_url", "duration_seconds", "published_at", "channel_id", "channel_title"}

    titles, cursor = [], None
    while True:
        page = on_client.get("/api/videos?limit=2" + (f"&cursor={cursor}" if cursor else "")).get_json()
        titles += [v["title"] for v in page["items"]]
        cursor = page["next_cursor"]
        if not cursor:
            break
    assert titles == ["A 하나", "C 하나", "A 둘", "C 둘", "A 셋"]
    assert on_client.get("/api/videos?cursor=nope").status_code == 400
    assert on_client.get("/api/videos?q=" + "가" * 51).status_code == 400


def test_videos_channel_filter(on_client, on_login, on_app, no_youtube):
    me = on_login()
    a = make_channel(on_app, "A", default=True, videos_=[("a1", 1, "A 하나")])
    b = make_channel(on_app, "B", default=True, videos_=[("b1", 1, "B 하나")], user_rows=[(me, True)])
    make_channel(on_app, "C", default=True, videos_=[("c1", 1, "C 하나")])
    assert [v["title"] for v in on_client.get(f"/api/videos?channel={a}").get_json()["items"]] == ["A 하나"]
    assert on_client.get(f"/api/videos?channel={b}").get_json()["items"] == []
    for bad in ("x", "", "-1", "99999999999"):
        assert on_client.get(f"/api/videos?channel={bad}").status_code == 400


def test_videos_search_escapes_like_wildcards(on_client, on_login, on_app, no_youtube):
    on_login()
    make_channel(on_app, "A", default=True, videos_=[("a1", 1, "할인 50% 장보기"), ("a2", 2, "된장_찌개"), ("a3", 3, "김치찌개")])
    search = lambda q: [v["title"] for v in on_client.get("/api/videos", query_string={"q": q}).get_json()["items"]]  # noqa: E731
    assert search("%") == ["할인 50% 장보기"]
    assert search("_") == ["된장_찌개"]
    assert search("  찌개 ") == ["된장_찌개", "김치찌개"]


def test_refresh_stale_limits_to_three_and_updates_fetched_at(on_client, on_login, on_app, monkeypatch):
    on_login()
    fresh = make_channel(on_app, "F", default=True)
    stale = [make_channel(on_app, name, default=True, fetched_ago=timedelta(hours=7 + i)) for i, name in enumerate("PQRS")]
    never = make_channel(on_app, "N", default=True, fetched_ago=None)
    asked = []

    def channel_info(key, channel_id=None, **kwargs):
        asked.append(channel_id)
        if channel_id == cid("S"):
            raise FetchError("HTTP500")
        return {"channel_id": channel_id, "title": "새 이름", "thumbnail_url": None, "uploads_playlist_id": "UUx", "video_count": 3}

    playlist_calls = []
    monkeypatch.setattr(outbound, "channel_info", channel_info)
    monkeypatch.setattr(outbound, "playlist_videos", lambda key, playlist_id: playlist_calls.append(playlist_id) or [])
    monkeypatch.setattr(outbound, "video_details", fail_if_called)  # 영상이 없으면 부르지 않는다

    assert on_client.get("/api/videos").status_code == 200
    assert asked == [cid("N"), cid("S"), cid("R")]  # 받은 적 없는 채널 → 오래된 순
    assert len(playlist_calls) == 2  # S는 실패
    with on_app.app_context():
        now = utcnow()
        fetched = {c.id: c.fetched_at for c in YoutubeChannel.query}
        refreshed = [never, stale[3], stale[2]]
        as_utc = lambda dt: dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)  # noqa: E731 SQLite는 tz 없이 돌려준다
        assert all(fetched[pk] is not None and abs(as_utc(fetched[pk]) - now) < timedelta(minutes=1) for pk in refreshed)
        assert db.session.get(YoutubeChannel, stale[3]).title == "채널 S"  # 실패하면 이름은 그대로
        assert db.session.get(YoutubeChannel, never).title == "새 이름"
    asked.clear()
    on_client.get("/api/videos")
    assert asked == [cid("Q"), cid("P")]  # 나머지 둘만, 방금 받은 채널·신선한 채널(F)은 다시 받지 않는다
    with on_app.app_context():
        assert db.session.get(YoutubeChannel, fresh).title == "채널 F"  # 한 번도 새로 받지 않았다
        assert AiCall.query.filter_by(kind="video_refresh").count() == 5  # 새로 받기마다 기록(실패 포함)


def test_refresh_replaces_videos_sets_duration_and_removes_gone_channel_videos(on_app, monkeypatch):
    pk = make_channel(on_app, "A", default=True, videos_=[("old", 1, "없어질 영상"), ("keep", 2, "옛 제목")])
    published = utcnow() - timedelta(days=1)
    monkeypatch.setattr(
        outbound,
        "channel_info",
        lambda key, channel_id: {"channel_id": channel_id, "title": "집밥 연구소", "thumbnail_url": "https://yt3.ggpht.com/a", "uploads_playlist_id": "UUa", "video_count": 248},
    )
    monkeypatch.setattr(
        outbound,
        "playlist_videos",
        lambda key, playlist_id: [
            {"video_id": vid("keep"), "title": "새 제목", "thumbnail_url": "https://i.ytimg.com/k.jpg", "published_at": published},
            {"video_id": vid("new"), "title": "새 영상", "thumbnail_url": None, "published_at": published},
        ],
    )
    detail_ids = []
    monkeypatch.setattr(
        outbound,
        "video_details",
        lambda key, ids: detail_ids.extend(ids) or {vid("keep"): {"duration_seconds": 724, "description": "재료: 돼지고기"}},
    )
    with on_app.app_context():
        videos.refresh_channel(db.session.get(YoutubeChannel, pk), "k")
        rows = {v.video_id: v for v in YoutubeVideo.query.filter_by(channel_id=pk)}
        assert set(rows) == {vid("keep"), vid("new")}
        assert (rows[vid("keep")].title, rows[vid("keep")].duration_seconds, rows[vid("keep")].description) == ("새 제목", 724, "재료: 돼지고기")
        assert rows[vid("new")].duration_seconds is None
        channel = db.session.get(YoutubeChannel, pk)
        assert (channel.title, channel.video_count, channel.thumbnail_url) == ("집밥 연구소", 248, "https://yt3.ggpht.com/a")
    assert detail_ids == [vid("keep"), vid("new")]

    monkeypatch.setattr(outbound, "channel_info", lambda key, channel_id: None)  # 삭제·비공개된 채널
    with on_app.app_context():
        videos.refresh_channel(db.session.get(YoutubeChannel, pk), "k")
        assert YoutubeVideo.query.count() == 0
        channel = db.session.get(YoutubeChannel, pk)
        assert (channel.thumbnail_url, channel.video_count, channel.uploads_playlist_id) == (None, None, None)
        assert videos.channel_json(channel)["unavailable"] is True

    make_channel(on_app, "B", default=True, videos_=[("b1", 1, "B")])
    monkeypatch.setattr(outbound, "channel_info", lambda key, channel_id: {"channel_id": channel_id, "title": "B", "thumbnail_url": None, "uploads_playlist_id": "UUb", "video_count": None})
    monkeypatch.setattr(outbound, "playlist_videos", lambda key, playlist_id: None)  # 재생목록 없음
    with on_app.app_context():
        videos.refresh_channel(YoutubeChannel.query.filter_by(channel_id=cid("B")).one(), "k")
        assert YoutubeVideo.query.count() == 0


def test_refresh_deletes_videos_older_than_30_days(on_client, on_login, on_app, no_youtube):
    on_login()
    pk = make_channel(on_app, "A", default=True, videos_=[("a1", 1, "새것"), ("a2", 2, "오래됨")])
    with on_app.app_context():
        old = YoutubeVideo.query.filter_by(video_id=vid("a2")).one()
        old.fetched_at = utcnow() - timedelta(days=31)
        db.session.commit()
    assert [v["title"] for v in on_client.get("/api/videos").get_json()["items"]] == ["새것"]
    with on_app.app_context():
        assert [v.video_id for v in YoutubeVideo.query.filter_by(channel_id=pk)] == [vid("a1")]


def test_video_detail_includes_description_and_channel(on_client, on_login, on_app, no_youtube):
    me = on_login()
    pk = make_channel(on_app, "A", default=True, videos_=[("a1", 3, "제육볶음")])
    hidden = make_channel(on_app, "H", default=True, videos_=[("h1", 3, "숨긴 채널 영상")], user_rows=[(me, True)])
    with on_app.app_context():
        video = YoutubeVideo.query.filter_by(video_id=vid("a1")).one()
        video.description = "재료 (3인분)"
        db.session.get(YoutubeChannel, pk).thumbnail_url = "https://yt3.ggpht.com/a"
        db.session.commit()
        video_pk = video.id
        hidden_video = YoutubeVideo.query.filter_by(channel_id=hidden).one().id
    body = on_client.get(f"/api/videos/{video_pk}").get_json()
    assert body["description"] == "재료 (3인분)" and body["video_id"] == vid("a1")
    assert (body["channel_id"], body["channel_title"], body["channel_thumbnail_url"]) == (pk, "채널 A", "https://yt3.ggpht.com/a")
    assert on_client.get(f"/api/videos/{hidden_video}").status_code == 404
    assert on_client.get("/api/videos/99999999999").status_code == 404


def channel_found(channel_id=cid("NEW"), title="집밥 연구소"):
    return {"channel_id": channel_id, "title": title, "thumbnail_url": None, "uploads_playlist_id": "UUnew", "video_count": 248}


def test_add_channel(on_client, on_login, on_app, monkeypatch):
    me = on_login()
    lookups = []
    monkeypatch.setattr(outbound, "channel_info", lambda key, **kw: lookups.append(kw) or channel_found())
    published = utcnow() - timedelta(days=1)
    monkeypatch.setattr(
        outbound,
        "playlist_videos",
        lambda key, playlist_id: [{"video_id": vid("n1"), "title": "첫 영상", "thumbnail_url": None, "published_at": published}],
    )
    monkeypatch.setattr(outbound, "video_details", lambda key, ids: {vid("n1"): {"duration_seconds": 511, "description": None}})

    res = on_client.post("/api/channels", json={"url": "https://www.youtube.com/@cookhouse"})
    assert res.status_code == 201
    body = res.get_json()
    assert (body["title"], body["video_count"], body["is_default"], body["hidden"]) == ("집밥 연구소", 248, False, False)
    assert lookups == [{"handle": "@cookhouse"}]
    assert [v["title"] for v in on_client.get("/api/videos").get_json()["items"]] == ["첫 영상"]  # 바로 받아 둠
    with on_app.app_context():
        assert [c.kind for c in AiCall.query.filter_by(user_id=me).order_by(AiCall.id)] == ["channel_add", "link_fetch", "video_refresh"]

    res = on_client.post("/api/channels", json={"url": "@cookhouse"})
    assert (res.status_code, res.get_json()["error"]) == (400, "이미 추가한 채널이에요.")
    res = on_client.post("/api/channels", json={"url": f"https://www.youtube.com/channel/{cid('NEW')}"})
    assert (res.status_code, res.get_json()["error"]) == (400, "이미 추가한 채널이에요.")
    assert len(lookups) == 2  # 채널 ID로 알고 있는 채널은 찾지 않는다

    res = on_client.post("/api/channels", json={"url": "https://recipe.example.com/@cookhouse"})
    assert (res.status_code, res.get_json()["error"]) == (400, videos.BAD_LINK)
    res = on_client.post("/api/channels", json={"url": "https://www.youtube.com/c/cookhouse"})
    assert (res.status_code, res.get_json()["error"]) == (400, videos.BAD_LINK)
    assert "@이름" in videos.BAD_LINK and "/channel/" in videos.BAD_LINK

    monkeypatch.setattr(outbound, "channel_info", lambda key, **kw: None)
    res = on_client.post("/api/channels", json={"url": "@nobody"})
    assert (res.status_code, res.get_json()["error"]) == (404, "채널을 찾을 수 없어요.")

    def boom(key, **kw):
        raise FetchError("HTTP403")

    monkeypatch.setattr(outbound, "channel_info", boom)
    res = on_client.post("/api/channels", json={"url": "@broken"})
    assert (res.status_code, res.get_json()["error"]) == (502, "채널 정보를 가져오지 못했어요. 잠시 후 다시 시도해주세요.")


def test_add_channel_default_cap_and_known_channel(on_client, on_login, on_app, monkeypatch):
    me = on_login()
    default = make_channel(on_app, "DEF", default=True, user_rows=[(me, True)])
    known = make_channel(on_app, "KNOWN", videos_=[("k1", 1, "남이 추가한 채널 영상")])
    monkeypatch.setattr(outbound, "channel_info", lambda key, **kw: channel_found(cid("DEF")))
    for name in ("playlist_videos", "video_details"):
        monkeypatch.setattr(outbound, name, fail_if_called)

    res = on_client.post("/api/channels", json={"url": "@default"})  # 숨긴 기본 채널 → 다시 보이기
    assert res.status_code == 200 and res.get_json()["id"] == default
    res = on_client.post("/api/channels", json={"url": "@default"})
    assert (res.status_code, res.get_json()["error"]) == (400, "기본 채널에 이미 있어요.")

    monkeypatch.setattr(outbound, "channel_info", fail_if_called)
    res = on_client.post("/api/channels", json={"url": f"youtube.com/channel/{cid('KNOWN')}"})
    assert res.status_code == 201 and res.get_json()["id"] == known  # 캐시된 채널 재사용, 외부 요청 없음

    with on_app.app_context():
        for i in range(29):
            channel = YoutubeChannel(channel_id=cid(f"M{i}"), title=f"{i}")
            db.session.add(channel)
            db.session.flush()
            db.session.add(UserChannel(user_id=me, channel_id=channel.id))
        db.session.commit()
    monkeypatch.setattr(outbound, "channel_info", lambda key, **kw: channel_found())
    res = on_client.post("/api/channels", json={"url": "@one-more"})
    assert (res.status_code, res.get_json()["error"]) == (400, "채널은 30개까지 추가할 수 있어요.")
    with on_app.app_context():
        assert UserChannel.query.filter_by(user_id=me, hidden=False).count() == 30


def test_add_channel_counts_toward_link_fetch_limit(on_client, on_login, on_app, monkeypatch):
    me = on_login()
    with on_app.app_context():
        db.session.add_all([AiCall(user_id=me, kind="link_fetch", created_at=utcnow()) for _ in range(5)])
        db.session.commit()
    monkeypatch.setattr(outbound, "channel_info", fail_if_called)
    res = on_client.post("/api/channels", json={"url": "@cookhouse"})
    assert (res.status_code, res.get_json()["error"]) == (429, "잠시 후 다시 시도해주세요.")


def test_channels_list_mine_first_then_defaults(on_client, on_login, on_app, no_youtube):
    me = on_login()
    make_channel(on_app, "D1", default=True)
    make_channel(on_app, "D2", default=True, user_rows=[(me, True)])
    make_channel(on_app, "D3", default=True, uploads=False)  # 새로 받아 보니 없어진 채널
    second = make_channel(on_app, "M2")
    first = make_channel(on_app, "M1")
    with on_app.app_context():
        db.session.add(UserChannel(user_id=me, channel_id=second, created_at=utcnow() - timedelta(days=1)))
        db.session.add(UserChannel(user_id=me, channel_id=first))
        db.session.commit()
    body = on_client.get("/api/channels").get_json()
    assert [(c["title"], c["is_default"], c["hidden"], c["unavailable"]) for c in body["items"]] == [
        ("채널 M2", False, False, False),
        ("채널 M1", False, False, False),
        ("채널 D1", True, False, False),
        ("채널 D2", True, True, False),
        ("채널 D3", True, False, True),
    ]
    assert (body["mine_count"], body["mine_limit"], body["sample"]) == (2, 30, False)


def test_hide_and_unhide_default_channel(on_client, on_login, on_app, no_youtube):
    me = on_login()
    default = make_channel(on_app, "D", default=True, videos_=[("d1", 1, "기본 영상")])
    mine = make_channel(on_app, "M", user_rows=[(me, False)])
    res = on_client.patch(f"/api/channels/{default}", json={"hidden": True})
    assert res.status_code == 200 and res.get_json()["hidden"] is True
    assert on_client.patch(f"/api/channels/{default}", json={"hidden": True}).status_code == 200  # 두 번 눌러도 된다
    with on_app.app_context():
        assert UserChannel.query.filter_by(user_id=me, channel_id=default).count() == 1
    assert on_client.get("/api/videos").get_json()["items"] == []
    res = on_client.patch(f"/api/channels/{default}", json={"hidden": False})
    assert res.status_code == 200 and res.get_json()["hidden"] is False
    assert len(on_client.get("/api/videos").get_json()["items"]) == 1
    assert on_client.patch(f"/api/channels/{mine}", json={"hidden": True}).status_code == 404
    assert on_client.patch(f"/api/channels/{default}", json={"hidden": "yes"}).status_code == 400
    assert on_client.patch("/api/channels/99999999999", json={"hidden": True}).status_code == 404
    mine_default = make_channel(on_app, "MD", default=True, user_rows=[(me, False)])  # 내가 추가한 뒤 기본 채널이 됨(내 채널 묶음)
    assert on_client.patch(f"/api/channels/{mine_default}", json={"hidden": True}).status_code == 404


def test_delete_my_channel_and_404_for_default_or_other_user(on_client, on_login, on_app, no_youtube):
    me = on_login()
    with on_app.app_context():
        other = User(provider="test", provider_id="other", nickname="o")
        db.session.add(other)
        db.session.commit()
        other_id = other.id
    mine = make_channel(on_app, "M", videos_=[("m1", 1, "내 채널 영상")], user_rows=[(me, False), (other_id, False)])
    default = make_channel(on_app, "D", default=True)
    others = make_channel(on_app, "O", user_rows=[(other_id, False)])
    assert on_client.delete(f"/api/channels/{default}").status_code == 404
    assert on_client.delete(f"/api/channels/{others}").status_code == 404
    assert on_client.delete("/api/channels/99999999999").status_code == 404
    assert on_client.delete(f"/api/channels/{mine}").status_code == 204
    assert on_client.delete(f"/api/channels/{mine}").status_code == 404
    with on_app.app_context():
        assert YoutubeVideo.query.filter_by(channel_id=mine).count() == 1  # 채널·영상은 남긴다(다른 사용자)
        assert UserChannel.query.filter_by(user_id=other_id).count() == 2


def test_seed_default_channels_cli(make_app, monkeypatch, tmp_path, no_youtube):
    app = make_app()
    kept = make_channel(app, "KEEP", default=True)
    dropped = make_channel(app, "DROP", default=True)
    data = tmp_path / "default_channels.json"
    data.write_text(f'[{{"channel_id": "{cid("KEEP")}", "name": "남는 채널"}}, {{"channel_id": "{cid("NEW")}", "name": "새 채널"}}]', encoding="utf-8")
    monkeypatch.setattr(videos, "DEFAULT_CHANNELS_FILE", data)
    result = app.test_cli_runner().invoke(args=["seed-default-channels"])
    assert result.exit_code == 0 and "기본 채널 2개를 맞췄어요." in result.output
    with app.app_context():
        assert db.session.get(YoutubeChannel, kept).is_default is True
        assert db.session.get(YoutubeChannel, dropped).is_default is False
        new = YoutubeChannel.query.filter_by(channel_id=cid("NEW")).one()
        assert (new.is_default, new.title, new.fetched_at) == (True, "새 채널", None)

    with app.app_context():
        count = YoutubeChannel.query.count()
    assert app.test_cli_runner().invoke(args=["seed-default-channels"]).exit_code == 0  # 다시 실행해도 같다
    with app.app_context():
        assert YoutubeChannel.query.count() == count

    refreshed = []
    monkeypatch.setattr(outbound, "channel_info", lambda key, channel_id: refreshed.append(channel_id))  # None → 채널 없음
    app.config["YOUTUBE_API_KEY"] = "k"
    assert app.test_cli_runner().invoke(args=["seed-default-channels"]).exit_code == 0
    assert refreshed == [cid("NEW")]  # KEEP은 6시간 안에 받았다

    data.write_text("[{", encoding="utf-8")
    result = app.test_cli_runner().invoke(args=["seed-default-channels"])
    assert result.exit_code != 0 and "읽지 못했어요(JSONDecodeError)" in result.output
    monkeypatch.setattr(videos, "DEFAULT_CHANNELS_FILE", tmp_path / "missing.json")
    result = app.test_cli_runner().invoke(args=["seed-default-channels"])
    assert result.exit_code != 0 and "읽지 못했어요(FileNotFoundError)" in result.output
    monkeypatch.setattr(videos, "DEFAULT_CHANNELS_FILE", data)

    data.write_text('[{"channel_id": "not-an-id"}]', encoding="utf-8")
    result = app.test_cli_runner().invoke(args=["seed-default-channels"])
    assert result.exit_code != 0 and "모양이어야 해요" in result.output


def test_shipped_default_channels_file_is_valid():
    """사용자가 확정한 기본 채널 목록(2026-09-14): seed-default-channels가 받는 모양이고 채널이 겹치지 않는다."""
    import json

    entries = json.loads(videos.DEFAULT_CHANNELS_FILE.read_text(encoding="utf-8"))
    ids = [e["channel_id"] for e in entries]
    assert entries and all(outbound.CHANNEL_ID.fullmatch(i) and e["name"].strip() for i, e in zip(ids, entries))
    assert len(set(ids)) == len(ids)


# --- 리뷰 반영: 쿼터 예산·첫 페이지만 새로 받기·페이지 경계 ---


def published(app, pk, name, when, title=None):
    with app.app_context():
        video = YoutubeVideo(video_id=vid(name), channel_id=pk, title=title or name, published_at=when, fetched_at=utcnow())
        db.session.add(video)
        db.session.commit()
        return video.id


def titles(res):
    assert res.status_code == 200, res.get_json()
    return [v["title"] for v in res.get_json()["items"]]


def test_refresh_budget_per_user_and_global_serves_cache(on_client, on_login, on_app, monkeypatch, no_youtube):
    me = on_login()
    with on_app.app_context():
        other = User(provider="test", provider_id="other", nickname="o")
        db.session.add(other)
        db.session.commit()
        other_id = other.id
    make_channel(on_app, "A", default=True, fetched_ago=timedelta(hours=7), videos_=[("a1", 1, "캐시된 영상")])

    with on_app.app_context():  # 사용자별 하루 20번을 다 썼다
        db.session.add_all([AiCall(user_id=me, kind="video_refresh", created_at=utcnow()) for _ in range(20)])
        db.session.commit()
    assert titles(on_client.get("/api/videos")) == ["캐시된 영상"]  # 오류 없이 캐시

    with on_app.app_context():  # 내 기록은 지우고, 다른 사용자들이 전체 예산을 다 썼다
        AiCall.query.filter_by(user_id=me).delete()
        db.session.add_all([AiCall(user_id=other_id, kind=kind, created_at=utcnow()) for kind in ("video_refresh", "channel_add")])
        db.session.commit()
    monkeypatch.setattr(videos, "DAILY_UNIT_BUDGET", 8)  # 3 + 3 쓰고 남은 2 < 3
    assert titles(on_client.get("/api/videos")) == ["캐시된 영상"]
    res = on_client.post("/api/channels", json={"url": "@cookhouse"})  # 처음 보는 채널 찾기도 막는다
    assert (res.status_code, res.get_json()["error"]) == (503, "지금은 채널을 추가할 수 없어요.")

    monkeypatch.setattr(videos, "DAILY_UNIT_BUDGET", 9)  # 딱 맞으면 받는다
    calls = []
    monkeypatch.setattr(outbound, "channel_info", lambda key, channel_id: calls.append(channel_id))
    on_client.get("/api/videos")
    assert calls == [cid("A")]


def test_video_rows_not_counted_as_ai_use(client, login, app):
    user = login()
    with app.app_context():
        db.session.add_all([AiCall(user_id=user.id, kind=kind, created_at=utcnow()) for kind in ("video_refresh", "channel_add", "link_fetch")])
        db.session.commit()
    usage = client.get("/api/ai-usage").get_json()
    assert (usage["scan"]["used"], usage["recipe"]["used"]) == (0, 0)
    with app.app_context():
        assert all(c.model is None and c.input_tokens is None for c in AiCall.query)


def test_channel_add_daily_limit_counts_every_add(on_client, on_login, on_app, monkeypatch):
    me = on_login()
    known = make_channel(on_app, "KNOWN")
    monkeypatch.setattr(outbound, "channel_info", fail_if_called)
    assert on_client.post("/api/channels", json={"url": f"youtube.com/channel/{cid('KNOWN')}"}).status_code == 201
    assert on_client.delete(f"/api/channels/{known}").status_code == 204
    with on_app.app_context():
        assert AiCall.query.filter_by(user_id=me, kind="channel_add").count() == 1  # 캐시된 채널 추가도 센다
        earlier = utcnow() - timedelta(minutes=5)
        db.session.add_all([AiCall(user_id=me, kind="channel_add", created_at=earlier) for _ in range(29)])
        db.session.commit()
    res = on_client.post("/api/channels", json={"url": f"youtube.com/channel/{cid('KNOWN')}"})
    assert (res.status_code, res.get_json()["error"]) == (429, "오늘 채널 추가는 30번까지 쓸 수 있어요. 내일 다시 써주세요.")


def test_refresh_stops_at_request_deadline(on_client, on_login, on_app, monkeypatch):
    on_login()
    for name in ("P", "Q"):
        make_channel(on_app, name, default=True, fetched_ago=None)
    clock = [1000.0]
    monkeypatch.setattr(videos.time, "monotonic", lambda: clock[0])
    asked = []

    def slow_channel_info(key, channel_id):
        asked.append(channel_id)
        clock[0] += videos.REQUEST_SECONDS + 1

    monkeypatch.setattr(outbound, "channel_info", slow_channel_info)
    assert on_client.get("/api/videos").status_code == 200
    assert asked == [cid("P")]


def test_refresh_only_on_first_page(on_client, on_login, on_app, no_youtube):
    on_login()
    pk = make_channel(on_app, "A", default=True, videos_=[("a1", 1, "하나"), ("a2", 2, "둘")])
    first = on_client.get("/api/videos?limit=1").get_json()
    with on_app.app_context():
        db.session.get(YoutubeChannel, pk).fetched_at = None  # 받아야 할 채널이지만
        old = YoutubeVideo.query.filter_by(video_id=vid("a1")).one()
        old.fetched_at = utcnow() - timedelta(days=31)
        db.session.commit()
    assert titles(on_client.get(f"/api/videos?limit=1&cursor={first['next_cursor']}")) == ["둘"]  # 유튜브를 부르지 않는다
    with on_app.app_context():
        assert YoutubeVideo.query.count() == 2  # 오래된 영상 지우기도 첫 페이지에서만(목록에서는 빠진다)


def test_videos_pagination_ties_filters_and_limits(on_client, on_login, on_app, no_youtube):
    on_login()
    a = make_channel(on_app, "A", default=True)
    b = make_channel(on_app, "B", default=True)
    same = utcnow() - timedelta(days=1)
    for i in range(3):
        published(on_app, a, f"tie{i}", same, f"같은 시각 찌개 {i}")
    published(on_app, b, "b1", same - timedelta(hours=1), "B 찌개")
    published(on_app, a, "a9", same - timedelta(hours=2), "A 볶음")

    def all_pages(query):
        got, cursor = [], None
        while True:
            body = on_client.get(f"/api/videos?limit=1{query}" + (f"&cursor={cursor}" if cursor else "")).get_json()
            got += [v["title"] for v in body["items"]]
            cursor = body["next_cursor"]
            if not cursor:
                return got

    assert all_pages("") == ["같은 시각 찌개 2", "같은 시각 찌개 1", "같은 시각 찌개 0", "B 찌개", "A 볶음"]
    assert all_pages("&q=찌개") == ["같은 시각 찌개 2", "같은 시각 찌개 1", "같은 시각 찌개 0", "B 찌개"]
    assert all_pages(f"&channel={a}") == ["같은 시각 찌개 2", "같은 시각 찌개 1", "같은 시각 찌개 0", "A 볶음"]

    for i in range(50):
        published(on_app, b, f"many{i}", same - timedelta(days=1, minutes=i))
    count = lambda limit: len(on_client.get(f"/api/videos?limit={limit}").get_json()["items"])  # noqa: E731
    assert (count(0), count(51), count("abc"), count(-5)) == (1, 50, 30, 1)


def test_videos_search_backslash_is_literal(on_client, on_login, on_app, no_youtube):
    on_login()
    make_channel(on_app, "A", default=True, videos_=[("a1", 1, "역슬래시 \\ 제목"), ("a2", 2, "보통 제목")])
    assert titles(on_client.get("/api/videos", query_string={"q": "\\"})) == ["역슬래시 \\ 제목"]


def test_old_video_detail_is_404(on_client, on_login, on_app, no_youtube):
    on_login()
    make_channel(on_app, "A", default=True, videos_=[("a1", 1, "오래됨")])
    with on_app.app_context():
        video = YoutubeVideo.query.one()
        video.fetched_at = utcnow() - timedelta(days=31)
        db.session.commit()
        video_pk = video.id
    assert on_client.get(f"/api/videos/{video_pk}").status_code == 404


def test_refresh_skips_video_already_under_another_channel(on_app, monkeypatch):
    make_channel(on_app, "OTHER", videos_=[("dup", 1, "다른 채널 영상")])
    pk = make_channel(on_app, "A", default=True)
    when = utcnow() - timedelta(days=1)
    monkeypatch.setattr(outbound, "playlist_videos", lambda key, playlist_id: [
        {"video_id": vid("dup"), "title": "겹침", "thumbnail_url": None, "published_at": when},
        {"video_id": vid("mine"), "title": "내 영상", "thumbnail_url": None, "published_at": when},
    ])
    monkeypatch.setattr(outbound, "video_details", lambda key, ids: {})
    info = {"channel_id": cid("A"), "title": "A", "thumbnail_url": None, "uploads_playlist_id": "UUa", "video_count": 2}
    with on_app.app_context():
        videos.refresh_channel(db.session.get(YoutubeChannel, pk), "k", info)
        assert {v.video_id: v.channel_id for v in YoutubeVideo.query.filter(YoutubeVideo.channel_id == pk)} == {vid("mine"): pk}
        assert YoutubeVideo.query.filter_by(video_id=vid("dup")).one().title == "다른 채널 영상"


def test_add_same_new_channel_race_reuses_row(on_client, on_login, on_app, monkeypatch):
    on_login()
    existing = make_channel(on_app, "NEW", fetched_ago=timedelta(0))  # 다른 사용자가 방금 추가한 행
    real_find, misses = videos.find_channel, [1]

    def racy_find(channel_id):  # 우리 요청이 확인할 때는 아직 없었다
        if misses:
            misses.pop()
            return None
        return real_find(channel_id)

    monkeypatch.setattr(videos, "find_channel", racy_find)
    monkeypatch.setattr(outbound, "channel_info", lambda key, **kw: channel_found())
    for name in ("playlist_videos", "video_details"):
        monkeypatch.setattr(outbound, name, fail_if_called)  # 이미 받아 둔 채널이라 새로 받지 않는다
    res = on_client.post("/api/channels", json={"url": "@cookhouse"})
    assert res.status_code == 201 and res.get_json()["id"] == existing
    with on_app.app_context():
        assert YoutubeChannel.query.filter_by(channel_id=cid("NEW")).count() == 1

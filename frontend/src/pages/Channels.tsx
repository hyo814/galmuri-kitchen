import { useEffect, useState, type FormEvent } from "react";
import { api, type Channel, type ChannelList } from "../api";
import Icon from "../components/Icon";
import { forgetResources, useResource } from "../useResource";
import { BackLink } from "./RecipeDetail";
import { setRecipesSegment } from "./Recipes";
import { Avatar } from "./VideoPlayer";

/** 채널이 바뀌면 영상 목록(모든 채널·검색 조합)과 칩 줄을 새로 받게 한다 */
function forgetVideoCaches() {
  forgetResources('list:["videos"');
  forgetResources("/api/channels");
}

/** 요리 채널: 채널 링크로 추가 · 내 채널 빼기 · 기본 채널 숨기기 (시안 Channels) */
export default function Channels() {
  const { data, error, reload } = useResource<ChannelList>("/api/channels");
  const [url, setUrl] = useState("");
  const [adding, setAdding] = useState(false);
  const [addError, setAddError] = useState("");
  const [busyId, setBusyId] = useState<number | null>(null);
  const [changeError, setChangeError] = useState("");
  useEffect(() => setRecipesSegment("video"), []); // 주소로 바로 열고 뒤로 가도 영상 칸으로

  const mine = data?.items.filter((c) => !c.is_default) ?? [];
  const defaults = data?.items.filter((c) => c.is_default) ?? [];

  const add = async (e: FormEvent) => {
    e.preventDefault();
    setAdding(true);
    setAddError("");
    setChangeError("");
    try {
      await api<Channel>("/api/channels", { method: "POST", body: { url: url.trim() } });
      setUrl("");
      forgetVideoCaches();
      await reload();
    } catch (err) {
      setAddError((err as Error).message);
    } finally {
      setAdding(false);
    }
  };

  const change = async (channel: Channel, request: () => Promise<unknown>) => {
    setBusyId(channel.id);
    setChangeError("");
    setAddError("");
    try {
      await request();
      forgetVideoCaches();
      await reload();
    } catch (err) {
      setChangeError((err as Error).message);
    } finally {
      setBusyId(null);
    }
  };

  const remove = (channel: Channel) => {
    if (!confirm("이 채널의 영상을 목록에서 뺄까요?")) return;
    change(channel, () => api(`/api/channels/${channel.id}`, { method: "DELETE" }));
  };

  const toggle = (channel: Channel) =>
    change(channel, () => api(`/api/channels/${channel.id}`, { method: "PATCH", body: { hidden: !channel.hidden } }));

  return (
    <main className="page">
      <BackLink label="영상" />
      <header className="topbar">
        <div>
          <h1>요리 채널</h1>
          <p className="summary">고른 채널의 새 영상만 보여줘요</p>
        </div>
      </header>

      <form className="r3-addrow" onSubmit={add} noValidate>
        <input
          className="input"
          type="url"
          inputMode="url"
          autoComplete="off"
          aria-label="채널 링크"
          aria-describedby={addError ? "channel-add-error" : undefined}
          aria-invalid={addError ? true : undefined}
          placeholder="채널 링크 붙여넣기"
          maxLength={500}
          value={url}
          onChange={(e) => setUrl(e.target.value)}
        />
        <button className="btn primary" disabled={adding || !url.trim()}>
          {adding ? "추가하는 중…" : "추가"}
        </button>
      </form>
      {addError && (
        <p className="error r3-add-error" id="channel-add-error" role="alert">
          {addError}
        </p>
      )}

      {!data ? (
        error ? (
          <div className="list-end">
            <p className="error" role="alert">
              {error}
            </p>
            <button className="btn secondary inline" onClick={reload}>
              <Icon name="refresh" size={16} />
              다시 불러오기
            </button>
          </div>
        ) : (
          <p className="center muted">불러오는 중…</p>
        )
      ) : (
        <>
          {changeError && (
            <p className="error r3-add-error" role="alert">
              {changeError}
            </p>
          )}
          <section aria-labelledby="channels-mine">
            <h2 className="r3-sechead" id="channels-mine">
              내 채널
              <span className="r3-count">
                {data.mine_count} / {data.mine_limit}
              </span>
            </h2>
            <ul className="list">
              {mine.length === 0 && <li className="r3-crow muted">아직 추가한 채널이 없어요.</li>}
              {mine.map((c) => (
                <li key={c.id} className="r3-crow">
                  <Avatar title={c.title} src={c.thumbnail_url} />
                  <span className="row-main">
                    <span className="row-title">{c.title}</span>
                    {c.unavailable ? (
                      <span className="row-sub">볼 수 없는 채널</span>
                    ) : (
                      c.video_count != null && <span className="row-sub">영상 {c.video_count.toLocaleString("ko-KR")}개</span>
                    )}
                  </span>
                  <button type="button" className="btn danger-sm" aria-label={`${c.title} 빼기`} disabled={busyId === c.id} onClick={() => remove(c)}>
                    빼기
                  </button>
                </li>
              ))}
            </ul>
          </section>

          {defaults.length > 0 && (
            <section aria-labelledby="channels-default">
              <h2 className="r3-sechead" id="channels-default">
                기본 채널
              </h2>
              <ul className="list">
                {defaults.map((c) => (
                  <li key={c.id} className="r3-crow">
                    <Avatar title={c.title} src={c.thumbnail_url} />
                    <span className="row-main">
                      <span className="row-title">{c.title}</span>
                      <span className="row-sub">
                        {c.unavailable ? "볼 수 없는 채널 · " : ""}
                        {c.hidden ? "숨겼어요" : "보여줘요"}
                      </span>
                    </span>
                    <button
                      type="button"
                      role="switch"
                      aria-checked={!c.hidden}
                      aria-label={`${c.title} 영상 보여주기`}
                      className="r3-toggle"
                      disabled={busyId === c.id}
                      onClick={() => toggle(c)}
                    />
                  </li>
                ))}
              </ul>
            </section>
          )}
        </>
      )}
    </main>
  );
}

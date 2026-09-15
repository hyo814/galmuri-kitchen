import { Fragment, useEffect, useRef, useState, type FormEvent } from "react";
import { api, type Channel, type ChannelList, type User } from "../api";
import Avatar from "../components/Avatar";
import Icon from "../components/Icon";
import { navigate } from "../useHashRoute";
import { forgetResources, useResource } from "../useResource";
import { BackLink } from "./RecipeDetail";
import { setRecipesSegment } from "./Recipes";

/** 채널이 바뀌면 영상 목록(모든 채널·검색 조합)과 칩 줄을 새로 받게 한다 */
function forgetVideoCaches() {
  forgetResources('list:["videos"');
  forgetResources("/api/channels");
}

/** 요리 채널: 채널 링크로 추가 · 내 채널 빼기 · 기본 채널 숨기기 (시안 Channels) */
export default function Channels({ user }: { user: User }) {
  const off = user.videos === "off";
  const { data, error, reload } = useResource<ChannelList>("/api/channels");
  const [url, setUrl] = useState("");
  const [adding, setAdding] = useState(false);
  const [addError, setAddError] = useState("");
  const [busyIds, setBusyIds] = useState<ReadonlySet<number>>(new Set());
  const [rowError, setRowError] = useState<{ id: number; message: string } | null>(null);
  // 빼기가 끝나 목록이 다시 그려지면 같은 순서의 빼기 버튼(없으면 `내 채널` 제목)으로 포커스
  const focusAfterRemove = useRef<number | null>(null);
  const mineRef = useRef<HTMLElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (off) navigate("/recipes", { replace: true }); // 영상을 쓸 수 없는데 주소로 바로 열었다
    else setRecipesSegment("video"); // 주소로 바로 열고 뒤로 가도 영상 칸으로
  }, [off]);

  useEffect(() => {
    const index = focusAfterRemove.current;
    if (index === null || !mineRef.current) return;
    focusAfterRemove.current = null;
    const buttons = mineRef.current.querySelectorAll<HTMLElement>(".btn.danger-sm");
    const target = buttons[Math.min(index, buttons.length - 1)] ?? mineRef.current.querySelector<HTMLElement>("h2");
    if (target?.tagName === "H2") target.tabIndex = -1;
    target?.focus();
  }, [data]);

  if (off) return null;

  const mine = data?.items.filter((c) => !c.is_default) ?? [];
  const defaults = data?.items.filter((c) => c.is_default) ?? [];
  const full = !!data && data.mine_count >= data.mine_limit;
  // 예시 모드·체험 계정은 서버가 바꾸기를 503으로 막으므로 누르지 못하게 한다(포커스는 남게 aria-disabled)
  const sample = !!data?.sample;
  const readOnly = sample || user.videos === "cached";
  const locked = readOnly ? { "aria-disabled": true, "aria-describedby": "channels-sample-note" } : {};

  const add = async (e: FormEvent) => {
    e.preventDefault();
    if (full || readOnly) return;
    setAdding(true);
    setAddError("");
    setRowError(null);
    try {
      await api<Channel>("/api/channels", { method: "POST", body: { url: url.trim() } });
      setUrl("");
      forgetVideoCaches();
      await reload();
    } catch (err) {
      setAddError((err as Error).message);
      inputRef.current?.focus(); // 고칠 수 있게 입력 칸으로(오류 문구는 aria-describedby로 읽힌다)
    } finally {
      setAdding(false);
    }
  };

  const change = async (channel: Channel, request: () => Promise<unknown>, onDone?: () => void) => {
    setBusyIds((prev) => new Set(prev).add(channel.id));
    setRowError(null);
    setAddError("");
    try {
      await request();
      onDone?.();
      forgetVideoCaches();
      await reload();
    } catch (err) {
      setRowError({ id: channel.id, message: (err as Error).message });
    } finally {
      setBusyIds((prev) => {
        const next = new Set(prev);
        next.delete(channel.id);
        return next;
      });
    }
  };

  const remove = (channel: Channel) => {
    if (readOnly || !confirm("이 채널의 영상을 목록에서 뺄까요?")) return;
    const index = mine.findIndex((c) => c.id === channel.id);
    change(channel, () => api(`/api/channels/${channel.id}`, { method: "DELETE" }), () => {
      focusAfterRemove.current = index;
    });
  };

  const toggle = (channel: Channel) =>
    !readOnly &&
    change(channel, () => api(`/api/channels/${channel.id}`, { method: "PATCH", body: { hidden: !channel.hidden } }));

  /** 실패한 줄 바로 아래의 오류 문구 */
  const errorRow = (channel: Channel) =>
    rowError?.id === channel.id && (
      <li className="r3-row-error">
        <p className="error" role="alert">
          {rowError.message}
        </p>
      </li>
    );

  return (
    <main className="page">
      <BackLink label="영상" />
      <header className="topbar">
        <div>
          <h1>요리 채널</h1>
          <p className="summary">고른 채널의 새 영상만 보여줘요</p>
        </div>
      </header>
      {sample && (
        <p className="rc-sample">
          <Icon name="info" size={16} />
          예시 채널로 보여줘요
        </p>
      )}

      <form className="r3-addrow" onSubmit={add} noValidate>
        <input
          ref={inputRef}
          className="input"
          type="url"
          inputMode="url"
          autoComplete="off"
          aria-label="채널 링크"
          aria-describedby={addError ? "channel-add-error" : full ? "channel-full" : readOnly ? "channels-sample-note" : undefined}
          aria-invalid={addError ? true : undefined}
          aria-disabled={readOnly || undefined}
          readOnly={readOnly}
          placeholder="채널 링크 붙여넣기"
          maxLength={500}
          disabled={full}
          value={url}
          onChange={(e) => {
            setUrl(e.target.value);
            setAddError("");
          }}
        />
        <button className="btn primary" disabled={!readOnly && (adding || full || !url.trim())} {...locked}>
          {adding ? "추가하는 중…" : "추가"}
        </button>
      </form>
      {addError ? (
        <p className="error r3-add-error" id="channel-add-error" role="alert">
          {addError}
        </p>
      ) : readOnly ? (
        <p className="hint r3-add-error" id="channels-sample-note">
          {sample ? "예시에서는 바꿀 수 없어요" : "체험 계정에서는 채널을 바꿀 수 없어요"}
        </p>
      ) : (
        full && (
          <p className="hint r3-add-error" id="channel-full">
            채널은 {data.mine_limit}개까지 추가할 수 있어요.
          </p>
        )
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
          <section aria-labelledby="channels-mine" ref={mineRef}>
            <h2 className="r3-sechead" id="channels-mine">
              내 채널
              <span className="r3-count">
                {data.mine_count} / {data.mine_limit}
              </span>
            </h2>
            <ul className="list">
              {mine.length === 0 && <li className="r3-crow muted">아직 추가한 채널이 없어요.</li>}
              {mine.map((c) => (
                <Fragment key={c.id}>
                  <li className="r3-crow">
                    <Avatar title={c.title} src={c.thumbnail_url} />
                    <span className="row-main">
                      <span className="row-title">{c.title}</span>
                      {c.unavailable ? (
                        <span className="row-sub">볼 수 없는 채널</span>
                      ) : (
                        c.video_count != null && <span className="row-sub">영상 {c.video_count.toLocaleString("ko-KR")}개</span>
                      )}
                    </span>
                    <button type="button" className="btn danger-sm" aria-label={`${c.title} 빼기`} disabled={busyIds.has(c.id)} {...locked} onClick={() => remove(c)}>
                      빼기
                    </button>
                  </li>
                  {errorRow(c)}
                </Fragment>
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
                  <Fragment key={c.id}>
                    <li className="r3-crow">
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
                        disabled={busyIds.has(c.id)}
                        {...locked}
                        onClick={() => toggle(c)}
                      />
                    </li>
                    {errorRow(c)}
                  </Fragment>
                ))}
              </ul>
            </section>
          )}
        </>
      )}
    </main>
  );
}

import { useEffect, useId, useRef, useState } from "react";
import {
  ApiError,
  api,
  localToday,
  type AiUsage,
  type MealKind,
  type MealPlan,
  type MealSlot,
  type MyRecipe,
  type RecipeChoice,
  type RecipeDraft,
  type User,
  type Video,
} from "../api";
import { remainingText, shortChannelName, timeAgo, withJosa } from "../format";
import { mealLabel, slotDateText } from "../meals/plan";
import { urgentLabel } from "../pages/Recipes";
import { Thumb } from "../pages/Videos";
import { useAsyncAction } from "../useAsyncAction";
import { forgetRecipeCaches, useResource } from "../useResource";
import Icon from "./Icon";
import Sheet from "./Sheet";

type Tab = "recipe" | "video" | "text";

const NEED_TEXT = "이 영상 설명에서는 레시피를 찾지 못했어요. 다른 영상을 골라주세요.";
const SLOT_FAILED = "레시피는 내 레시피에 저장했어요. 칸에는 넣지 못했어요. 내 레시피 칸에서 다시 넣어주세요.";

interface Props {
  plan: MealPlan;
  date: string;
  meal: MealKind;
  /** 다른 걸로 바꾸기: 지금 칸(인분을 이어받는다) */
  current?: MealSlot;
  user: User;
  onSaved: (slot: MealSlot) => void;
  onClose: () => void;
}

/** 검색 글자가 멈추고 300ms 뒤 다시 받는다(빈 칸이면 바로). 앞 요청은 끊는다. result.q는 목록이 어떤 검색어의 결과인지 */
function useSearch<T>(path: string, input: string, enabled = true) {
  const [result, setResult] = useState<{ q: string; items: T[] } | null>(null);
  const [error, setError] = useState("");
  const [retries, setRetries] = useState(0);
  const q = input.trim();

  useEffect(() => {
    if (!enabled) return;
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      setError("");
      try {
        const data = await api<{ items: T[] }>(`${path}${path.includes("?") ? "&" : "?"}q=${encodeURIComponent(q)}`, { signal: controller.signal });
        setResult({ q, items: data.items });
      } catch (e) {
        if (!controller.signal.aborted) setError((e as Error).message);
      }
    }, q ? 300 : 0);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [path, q, enabled, retries]);

  return { result, error, retry: () => setRetries((n) => n + 1) };
}

function SearchBox({ label, value, disabled, onChange }: { label: string; value: string; disabled?: boolean; onChange: (value: string) => void }) {
  return (
    <div className="r3-search ml-sheet-search">
      <label>
        <Icon name="search" size={20} />
        <span className="sr-only">{label}</span>
        <input type="search" placeholder={label} maxLength={50} enterKeyHint="search" value={value} disabled={disabled} onChange={(e) => onChange(e.target.value)} />
      </label>
    </div>
  );
}

function ListState({ error, loading, empty, onRetry }: { error: string; loading: boolean; empty: string; onRetry: () => void }) {
  if (error)
    return (
      <div className="center">
        <p className="error" role="alert">
          {error}
        </p>
        <button type="button" className="btn secondary inline" onClick={onRetry}>
          <Icon name="refresh" size={16} />
          다시 불러오기
        </button>
      </div>
    );
  return <p className="center muted">{loading ? "불러오는 중…" : empty}</p>;
}

/** 시안 FillRecipe·FillVideo·FillText: 빈 칸 채우기·다른 걸로 바꾸기 */
export default function MealFillSheet({ plan, date, meal, current, user, onSaved, onClose }: Props) {
  const videosOn = user.videos !== "off";
  const tabs: [Tab, string][] = [["recipe", "내 레시피"], ...(videosOn ? [["video", "영상"] as [Tab, string]] : []), ["text", "직접 쓰기"]];
  const [tab, setTab] = useState<Tab>("recipe");
  const [servings, setServings] = useState(current?.servings ?? plan.default_servings);
  // 칸을 오가도 고른 것·입력은 그대로(칸마다 따로 둔다)
  const [recipeInput, setRecipeInput] = useState("");
  const [recipeId, setRecipeId] = useState<number | null>(null);
  const [videoInput, setVideoInput] = useState("");
  const [videoId, setVideoId] = useState<number | null>(null);
  const [title, setTitle] = useState("");
  const { busy, error, setError, run } = useAsyncAction();
  const [importing, setImporting] = useState(false);
  const [importError, setImportError] = useState("");
  const abortRef = useRef<AbortController | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const { data: usage, reload: reloadUsage } = useResource<AiUsage>("/api/ai-usage");
  const recipes = useSearch<RecipeChoice>("/api/recipes/choices", recipeInput);
  const videos = useSearch<Video>("/api/videos?limit=20", videoInput, videosOn);
  const radioName = useId();
  const servingsLabel = useId();
  const titleId = useId();
  const titleHint = useId();

  // 시트를 닫으면(취소·뒤로가기·배경 탭) 영상 정리 요청도 끊는다
  useEffect(() => () => abortRef.current?.abort(), []);

  // 검색으로 목록에서 빠진 것은 고른 것으로 치지 않는다(검색을 지우면 다시 고른 채로 보인다)
  const pickedRecipe = recipes.result?.items.find((r) => r.id === recipeId);
  const pickedVideo = videos.result?.items.find((v) => v.id === videoId);
  const working = busy || importing;
  const canSave = tab === "recipe" ? !!pickedRecipe : tab === "video" ? !!pickedVideo : !!title.trim();

  const putSlot = (body: { recipe_id: number } | { title: string }, signal?: AbortSignal) =>
    api<MealSlot>(`/api/meal-plans/${plan.id}/slots`, { method: "PUT", body: { date, meal, servings, ...body }, signal });

  /** 영상: 확인 화면 없이 정리 → 내 레시피에 저장 → 칸에 넣기(스펙 20절) */
  const importVideo = async (video: Video) => {
    const controller = new AbortController();
    abortRef.current = controller;
    const { signal } = controller;
    setImporting(true);
    setImportError("");
    let stage: "import" | "recipe" | "slot" = "import";
    try {
      const draft = await api<RecipeDraft>("/api/recipes/import", {
        method: "POST",
        body: { url: `https://www.youtube.com/watch?v=${video.video_id}` },
        signal,
      });
      stage = "recipe";
      const { title, servings: recipeServings, ingredients, steps, source_url } = draft;
      const recipe = await api<MyRecipe>("/api/recipes", {
        method: "POST",
        body: { title, servings: recipeServings, ingredients, steps, source: "youtube", source_url },
        signal,
      });
      stage = "slot";
      await onSaved(await putSlot({ recipe_id: recipe.id }, signal));
    } catch (e) {
      if (signal.aborted) return;
      setImporting(false);
      setImportError(
        stage === "slot"
          ? SLOT_FAILED
          : stage === "import" && e instanceof ApiError && e.body?.need_text === true
            ? NEED_TEXT
            : (e as Error).message,
      );
    } finally {
      if (stage !== "import") forgetRecipeCaches(); // 도중에 끊겨도 서버에는 저장됐을 수 있다
      void reloadUsage();
    }
  };

  const save = () => {
    if (!canSave || working) return;
    if (tab === "video") return void importVideo(pickedVideo!);
    run(async () => onSaved(await putSlot(tab === "recipe" ? { recipe_id: pickedRecipe!.id } : { title: title.trim() })));
  };

  // dialog.close()로 닫아야 여는 버튼으로 포커스가 돌아간다(close 이벤트가 onClose를 부른다)
  const close = () => rootRef.current?.querySelector("dialog")?.close();

  const videoQ = videos.result?.q ?? "";

  return (
    <div ref={rootRef}>
      <Sheet title={`${mealLabel(meal)} 채우기`} description={slotDateText(date, localToday())} onClose={onClose}>
        <div
          className="segmented"
          role="group"
          aria-label="채우는 방법"
          style={{ gridTemplateColumns: `repeat(${tabs.length}, minmax(0, 1fr))` }}
        >
          {tabs.map(([key, label]) => (
            <button
              key={key}
              type="button"
              aria-pressed={tab === key}
              disabled={importing}
              onClick={() => {
                setTab(key);
                setError("");
              }}
            >
              {label}
            </button>
          ))}
        </div>

        {tab === "recipe" && (
          <>
            <SearchBox label="내 레시피에서 찾기" value={recipeInput} onChange={setRecipeInput} />
            {recipes.result?.items.length ? (
              <div className="ml-picks" role="radiogroup" aria-label="내 레시피">
                {recipes.result.items.map((recipe) => (
                  <label key={recipe.id} className="mo-radio">
                    <input
                      className="sr-only"
                      type="radio"
                      name={`${radioName}-recipe`}
                      checked={recipe.id === recipeId}
                      onChange={() => setRecipeId(recipe.id)}
                    />
                    <span className="mo-dot" aria-hidden="true" />
                    <span className="row-main">
                      {recipe.urgent_names.length > 0 && <span className="sh-tag warn">{urgentLabel(recipe.urgent_names)}</span>}
                      <span className="row-title">{recipe.title}</span>
                      <span className="rc-match">
                        재료 {recipe.total_count}개 중 <b>{recipe.have_count}개</b> 있어요
                      </span>
                    </span>
                  </label>
                ))}
              </div>
            ) : (
              <ListState
                error={recipes.error}
                loading={!recipes.result}
                empty={recipes.result?.q ? "찾는 레시피가 없어요" : "아직 내 레시피가 없어요. 영상이나 직접 쓰기로 채워주세요"}
                onRetry={recipes.retry}
              />
            )}
          </>
        )}

        {tab === "video" && (
          <>
            <SearchBox label="영상 제목에서 찾기" value={videoInput} disabled={importing} onChange={setVideoInput} />
            {videos.result?.items.length ? (
              <div className="ml-vlist" role="radiogroup" aria-label="영상">
                {videos.result.items.map((video) => (
                  <label key={video.id} className="r3-vrow">
                    <input
                      className="sr-only"
                      type="radio"
                      name={`${radioName}-video`}
                      checked={video.id === videoId}
                      disabled={importing}
                      onChange={() => setVideoId(video.id)}
                    />
                    <Thumb video={video} />
                    <span className="r3-vtext">
                      <span className="r3-vtitle">{video.title}</span>
                      <span className="r3-vsub">
                        {shortChannelName(video.channel_title)} · {timeAgo(video.published_at)}
                      </span>
                    </span>
                  </label>
                ))}
              </div>
            ) : (
              <ListState
                error={videos.error}
                loading={!videos.result}
                empty={videoQ ? `'${videoQ}'${withJosa(videoQ, "이", "가").slice(videoQ.length)} 들어간 영상이 없어요.` : "아직 모아 둔 영상이 없어요."}
                onRetry={videos.retry}
              />
            )}
            {importing && (
              <div className="ml-status" role="status">
                <b>
                  <span className="r3-dots" aria-hidden="true">
                    <i />
                    <i />
                    <i />
                  </span>
                  영상에서 레시피를 정리하고 있어요
                </b>
                <span>10초쯤 걸려요. 다 되면 내 레시피에 저장하고 이 칸에 {servings}인분으로 넣어줘요.</span>
              </div>
            )}
            {importError && (
              <p className="error" role="alert">
                {importError}
              </p>
            )}
          </>
        )}

        {tab === "text" && (
          <div className="field">
            <label className="field-label" htmlFor={titleId}>
              무엇을 먹을까요?
            </label>
            <input
              id={titleId}
              className="input"
              placeholder="라면에 달걀 하나"
              maxLength={60}
              autoComplete="off"
              aria-describedby={titleHint}
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.nativeEvent.isComposing) save();
              }}
            />
            <p className="ml-hint" id={titleHint}>
              레시피 없이 이름만 적어요. 재료를 몰라서 장보기 목록에는 들어가지 않아요
            </p>
          </div>
        )}

        {!importing && (
          <div className="field ml-serv-field" role="group" aria-labelledby={servingsLabel}>
            <span className="field-label" id={servingsLabel}>
              인분
            </span>
            <div className="stepper">
              <button type="button" className="icon-btn" aria-label="인분 줄이기" disabled={servings <= 1} onClick={() => setServings(servings - 1)}>
                <Icon name="minus" />
              </button>
              <output className="input rc-count" aria-live="polite">
                {servings}인분
              </output>
              <button type="button" className="icon-btn" aria-label="인분 늘리기" disabled={servings >= 20} onClick={() => setServings(servings + 1)}>
                <Icon name="plus" />
              </button>
            </div>
          </div>
        )}

        {error && tab !== "video" && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        <div className="actions">
          <button type="button" className="btn outline" onClick={close}>
            취소
          </button>
          {/* 고른 게 없거나 넣는 동안에도 disabled 대신 aria-disabled — 포커스가 버튼에 남는다 */}
          <button type="button" className="btn primary" aria-disabled={!canSave || working || undefined} aria-busy={working || undefined} onClick={save}>
            {importing ? "정리하는 중" : busy ? "넣는 중…" : "넣기"}
          </button>
        </div>
        {tab === "video" && <p className="r3-quota ml-quota">영상은 AI가 정리해요{remainingText(usage)}</p>}
      </Sheet>
    </div>
  );
}

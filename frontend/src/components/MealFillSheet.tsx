import { useEffect, useId, useRef, useState } from "react";
import {
  ApiError,
  api,
  isMultiImport,
  localToday,
  type AiUsage,
  type MealKind,
  type MealPlan,
  type MealSlot,
  type MultiRecipeDraft,
  type MyRecipe,
  type RecipeChoice,
  type RecipeDraft,
  type RecipeInput,
  type User,
  type Video,
} from "../api";
import { remainingText, shortChannelName, timeAgo, withJosa } from "../format";
import { mealLabel, slotDateText } from "../meals/plan";
import { urgentLabel } from "../pages/Recipes";
import { useAsyncAction } from "../useAsyncAction";
import { forgetRecipeCaches, useResource } from "../useResource";
import Icon from "./Icon";
import RecipePickSheet from "./RecipePickSheet";
import Sheet from "./Sheet";
import Thumb from "./VideoThumb";

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
  /** 넣는 중에 시트를 닫았다: 요청은 끊었지만 서버에는 들어갔을 수 있어 식단을 다시 받는다 */
  onInterrupted: () => void;
  onClose: () => void;
}

/** 검색 글자가 멈추고 300ms 뒤 다시 받는다(빈 칸이면 바로). 앞 요청은 끊는다. result.q는 목록이 어떤 검색어의 결과인지.
 *  요리 일기 쓰기 시트(DiaryWriteSheet)도 쓴다 */
export function useSearch<T>(path: string, input: string, enabled = true) {
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

export function SearchBox({ label, value, disabled, onChange }: { label: string; value: string; disabled?: boolean; onChange: (value: string) => void }) {
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

/** compact: 지난 목록 위에 붙이는 작은 오류(목록이 없을 때는 가운데 크게) */
export function ListState({ error, loading, empty, onRetry, compact }: { error: string; loading: boolean; empty: string; onRetry: () => void; compact?: boolean }) {
  if (error)
    return (
      <div className={compact ? "list-end ml-refetch" : "center"}>
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
export default function MealFillSheet({ plan, date, meal, current, user, onSaved, onInterrupted, onClose }: Props) {
  const videosOn = user.videos !== "off";
  const tabs: [Tab, string][] = [["recipe", "내 레시피"], ...(videosOn ? [["video", "영상"] as [Tab, string]] : []), ["text", "직접 쓰기"]];
  const [tab, setTab] = useState<Tab>("recipe");
  // 영상 목록은 영상 탭을 처음 열 때 받는다(검색 없는 첫 페이지는 서버가 오래된 채널을 새로 받아 몇 초 걸릴 수 있다)
  const [videoOpened, setVideoOpened] = useState(false);
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
  // 여러 요리 가져오기(17절): 영상 설명에 요리가 여러 개면 고르고 나서 이어간다(remaining을 남기지 않는다 — 이 칸 하나만 채우면 끝)
  const [multiPick, setMultiPick] = useState<{ result: MultiRecipeDraft; sourceUrl: string } | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const { data: usage, reload: reloadUsage } = useResource<AiUsage>("/api/ai-usage");
  const recipes = useSearch<RecipeChoice>("/api/recipes/choices", recipeInput);
  const videos = useSearch<Video>("/api/videos?limit=20", videoInput, videosOn && videoOpened);
  const radioName = useId();
  const servingsLabel = useId();
  const titleId = useId();
  const titleHint = useId();

  // 시트를 닫으면(취소·뒤로가기·배경 탭) 넣는 중인 요청(영상 정리·칸 넣기)도 끊고 식단을 다시 받게 한다
  const interrupted = useRef(onInterrupted);
  interrupted.current = onInterrupted;
  useEffect(
    () => () => {
      if (!abortRef.current) return;
      abortRef.current.abort();
      interrupted.current();
    },
    [],
  );

  // 검색으로 목록에서 빠진 것은 고른 것으로 치지 않는다(검색을 지우면 다시 고른 채로 보인다)
  const pickedRecipe = recipes.result?.items.find((r) => r.id === recipeId);
  const pickedVideo = videos.result?.items.find((v) => v.id === videoId);
  const working = busy || importing;
  const canSave = tab === "recipe" ? !!pickedRecipe : tab === "video" ? !!pickedVideo : !!title.trim();

  const putSlot = (body: { recipe_id: number } | { title: string }, signal?: AbortSignal) =>
    api<MealSlot>(`/api/meal-plans/${plan.id}/slots`, { method: "PUT", body: { date, meal, servings, ...body }, signal });

  /** 영상: 확인 화면 없이 정리 → 내 레시피에 저장 → 칸에 넣기(스펙 20절). 설명에 요리가 여러 개면(17절) 고른 뒤 이어간다(AI는 다시 안 부른다) */
  const importVideo = async (video: Video) => {
    const controller = new AbortController();
    abortRef.current = controller;
    const { signal } = controller;
    setImporting(true);
    setImportError("");
    const sourceUrl = `https://www.youtube.com/watch?v=${video.video_id}`;
    try {
      const result = await api<RecipeDraft | MultiRecipeDraft>("/api/recipes/import", { method: "POST", body: { url: sourceUrl }, signal });
      if (signal.aborted) return;
      if (isMultiImport(result)) {
        setImporting(false);
        setMultiPick({ result, sourceUrl });
        return;
      }
      await saveVideoRecipe(result, sourceUrl, controller);
    } catch (e) {
      if (signal.aborted) return;
      setImporting(false);
      setImportError(e instanceof ApiError && e.body?.need_text === true ? NEED_TEXT : (e as Error).message);
    } finally {
      if (abortRef.current === controller) abortRef.current = null;
      void reloadUsage();
    }
  };

  /** 여러 요리 중 하나를 골라 저장 → 칸 넣기를 이어간다. 이 칸 하나만 채우면 끝이라 나머지는 남기지 않는다(17절과 달리 세션이 없다) */
  const pickVideoRecipe = (order: number) => {
    if (!multiPick) return;
    const { result, sourceUrl } = multiPick;
    setMultiPick(null);
    const controller = new AbortController();
    abortRef.current = controller;
    setImporting(true);
    void saveVideoRecipe(result.recipes[order - 1], sourceUrl, controller);
  };

  /** 정리된 레시피 하나를 내 레시피에 저장하고 칸에 넣는다(importVideo·여러 요리 고르기 이후가 함께 쓴다) */
  const saveVideoRecipe = async (draft: RecipeInput, sourceUrl: string, controller: AbortController) => {
    const { signal } = controller;
    let recipe: MyRecipe | undefined;
    try {
      recipe = await api<MyRecipe>("/api/recipes", { method: "POST", body: { ...draft, source: "youtube", source_url: sourceUrl }, signal });
      const slot = await putSlot({ recipe_id: recipe.id }, signal);
      abortRef.current = null; // 다 넣었다: 이제 닫혀도 끊긴 요청이 아니다
      await onSaved(slot);
    } catch (e) {
      if (signal.aborted) return;
      setImporting(false);
      if (recipe) {
        // 레시피는 저장됐다: 넣기를 다시 눌러 같은 영상을 또 정리(중복 레시피·AI 횟수)하지 않게 영상 선택을 풀고,
        // 내 레시피 칸에서 방금 저장한 레시피를 골라 둔다(제목으로 검색해 목록 50개 밖이어도 보이게)
        setVideoId(null);
        setRecipeInput(recipe.title);
        setRecipeId(recipe.id);
        recipes.retry(); // 같은 검색어였어도 새 레시피가 들어오게 다시 받는다
        setTab("recipe");
        setError(SLOT_FAILED);
        return;
      }
      setImportError((e as Error).message);
    } finally {
      if (abortRef.current === controller) abortRef.current = null;
      forgetRecipeCaches(); // 도중에 끊겨도 서버에는 저장됐을 수 있다
      void reloadUsage();
    }
  };

  const save = () => {
    if (!canSave || working) return;
    if (tab === "video") return void importVideo(pickedVideo!);
    run(async () => {
      const controller = new AbortController();
      abortRef.current = controller;
      try {
        const slot = await putSlot(tab === "recipe" ? { recipe_id: pickedRecipe!.id } : { title: title.trim() }, controller.signal);
        abortRef.current = null;
        await onSaved(slot);
      } finally {
        if (abortRef.current === controller) abortRef.current = null;
      }
    });
  };

  // dialog.close()로 닫아야 여는 버튼으로 포커스가 돌아간다(close 이벤트가 onClose를 부른다)
  const close = () => rootRef.current?.querySelector("dialog")?.close();

  const videoQ = videos.result?.q ?? "";

  // 여러 요리 가져오기(17절): 고르는 동안은 탭·검색을 감춘다(취소하면 그대로 돌아온다 — 다른 상태는 그대로 있다)
  if (multiPick) {
    return (
      <div ref={rootRef}>
        <RecipePickSheet
          title={`요리가 ${multiPick.result.recipes.length}개 있어요`}
          subtitle="이 칸에 넣을 요리를 골라주세요"
          items={multiPick.result.recipes.map((draft, i) => ({ order: i + 1, draft }))}
          fromImage={multiPick.result.from_image}
          imagesTruncated={multiPick.result.images_truncated}
          note="AI는 1번만 썼어요."
          onPick={pickVideoRecipe}
          onClose={() => setMultiPick(null)}
        />
      </div>
    );
  }

  return (
    <div ref={rootRef}>
      <Sheet title={`${mealLabel(meal)} 채우기`} description={slotDateText(date, localToday())} onClose={onClose}>
        {/* 알림은 처음부터 붙어 있는 영역에 글자만 바꿔 넣는다 — 글자와 함께 새로 붙인 영역은 TalkBack이 읽지 않을 수 있다.
            sr-only(absolute)라 시트 간격(gap)을 차지하지 않는다. 화면에 보이는 상자·오류는 아래에 따로 그린다 */}
        <p className="sr-only" role="status">
          {importing ? `영상에서 레시피를 정리하고 있어요. 10초쯤 걸려요. 다 되면 내 레시피에 저장하고 이 칸에 ${servings}인분으로 넣어줘요.` : ""}
        </p>
        <p className="sr-only" role="alert">
          {tab === "video" ? importError : error}
        </p>
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
                if (key === "video") setVideoOpened(true);
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
              <>
                {/* 다시 받기에 실패해도 지난 목록은 두고 오류를 위에 알린다 */}
                {recipes.error && <ListState error={recipes.error} loading={false} empty="" onRetry={recipes.retry} compact />}
                <div className="ml-picks" role="radiogroup" aria-label="내 레시피">
                  {recipes.result.items.map((recipe) => (
                    <label key={recipe.id} className="mo-radio">
                      {/* 이름은 제목만, 태그·재료 수는 설명으로(읽는 이름이 길어지지 않게) */}
                      <input
                        className="sr-only"
                        type="radio"
                        name={`${radioName}-recipe`}
                        checked={recipe.id === recipeId}
                        aria-label={recipe.title}
                        aria-describedby={
                          [recipe.urgent_names.length > 0 && `${radioName}-r${recipe.id}-tag`, recipe.total_count > 0 && `${radioName}-r${recipe.id}-match`]
                            .filter(Boolean)
                            .join(" ") || undefined
                        }
                        onChange={() => setRecipeId(recipe.id)}
                      />
                      <span className="mo-dot" aria-hidden="true" />
                      <span className="row-main">
                        {recipe.urgent_names.length > 0 && (
                          <span className="sh-tag warn" id={`${radioName}-r${recipe.id}-tag`}>
                            {urgentLabel(recipe.urgent_names)}
                          </span>
                        )}
                        <span className="row-title">{recipe.title}</span>
                        {recipe.total_count > 0 && (
                          <span className="rc-match" id={`${radioName}-r${recipe.id}-match`}>
                            재료 {recipe.total_count}개 중 <b>{recipe.have_count}개</b> 있어요
                          </span>
                        )}
                      </span>
                    </label>
                  ))}
                </div>
              </>
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
            <SearchBox label="영상 제목·설명에서 찾기" value={videoInput} disabled={importing} onChange={setVideoInput} />
            {videos.result?.items.length ? (
              <>
                {videos.error && <ListState error={videos.error} loading={false} empty="" onRetry={videos.retry} compact />}
                <div className="ml-vlist" role="radiogroup" aria-label="영상">
                  {videos.result.items.map((video) => (
                    <label key={video.id} className="r3-vrow">
                      <input
                        className="sr-only"
                        type="radio"
                        name={`${radioName}-video`}
                        checked={video.id === videoId}
                        aria-label={video.title}
                        aria-describedby={`${radioName}-v${video.id}-sub`}
                        disabled={importing}
                        onChange={() => {
                          setVideoId(video.id);
                          setImportError("");
                        }}
                      />
                      <Thumb video={video} />
                      <span className="r3-vtext">
                        <span className="r3-vtitle">{video.title}</span>
                        <span className="r3-vsub" id={`${radioName}-v${video.id}-sub`}>
                          {shortChannelName(video.channel_title)} · {timeAgo(video.published_at)}
                        </span>
                      </span>
                    </label>
                  ))}
                </div>
              </>
            ) : (
              <ListState
                error={videos.error}
                loading={!videos.result}
                empty={videoQ ? `'${videoQ}'${withJosa(videoQ, "이", "가").slice(videoQ.length)} 들어간 영상이 없어요.` : "아직 모아 둔 영상이 없어요."}
                onRetry={videos.retry}
              />
            )}
            {importing && (
              <div className="ml-status">
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
            {importError && <p className="error">{importError}</p>}
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

        {error && tab !== "video" && <p className="error">{error}</p>}
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

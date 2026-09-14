import { useState, type ReactNode } from "react";
import { ApiError, localToday, type MealPlan, type MealShoppingPreview, type MealShoppingRow } from "../api";
import Icon from "../components/Icon";
import Mascot from "../components/Mascot";
import { addedText, cut } from "../components/ShoppingAddButton";
import { buyDayText, previewDetail, rangeText } from "../meals/plan";
import { quantityText } from "../shopping/sync";
import { addMany } from "../shopping/useShopping";
import { goBack, navigate } from "../useHashRoute";
import { forgetResources, useResource } from "../useResource";
import { LoadError } from "./Meals";
import { showShoppingNotice } from "./Shopping";
import { BackLink } from "./RecipeDetail";

const TITLE = "장보기 목록 만들기";
const OFFLINE = "인터넷이 연결되면 담을 수 있어요";
const BULK_MAX = 50; // 서버 한 번에 담기 상한

/** #/meals/:id/shopping — 식단 레시피 칸의 재료를 재고·장보기 목록과 비교해 담는다(시안 ShoppingPreview) */
export default function MealShopping({ id }: { id: string }) {
  const url = `/api/meal-plans/${id}/shopping-preview`;
  const preview = useResource<MealShoppingPreview>(url);
  const plan = useResource<MealPlan>(`/api/meal-plans/${id}`); // 장보기 태그 이름(source_label)
  const data = preview.data;
  return (
    <main className="page">
      <BackLink to="/meals" label="식단" />
      <header className="topbar">
        <div>
          <h1>{TITLE}</h1>
          {data && data.recipe_slot_count > 0 && (
            <p className="summary">
              {rangeText(data.start_on, data.end_on)} · 레시피가 있는 칸 {data.recipe_slot_count}개의 재료예요
            </p>
          )}
        </div>
      </header>
      {data ? (
        data.recipe_slot_count === 0 ? (
          <section className="empty rc-empty ml-empty">
            <Mascot size={72} />
            <p className="soon-title">레시피가 있는 칸이 없어요</p>
            {/* 서버는 오늘부터 계산해 기간이 모두 지나면 start_on이 end_on 뒤다 */}
            <p className="muted">{data.start_on > data.end_on ? "지난 끼니는 계산하지 않아요" : "레시피로 칸을 채우면 필요한 재료를 계산해줘요"}</p>
            <button type="button" className="btn primary inline" onClick={() => goBack("/meals")}>
              식단으로 돌아가기
            </button>
          </section>
        ) : (
          <Preview data={data} url={url} planName={plan.data?.name} />
        )
      ) : preview.status === 404 ? (
        <p className="center muted">식단을 찾을 수 없어요.</p>
      ) : preview.error ? (
        <LoadError error={preview.error} onRetry={preview.reload} />
      ) : (
        <p className="center muted">불러오는 중…</p>
      )}
    </main>
  );
}

function Preview({ data, url, planName }: { data: MealShoppingPreview; url: string; planName?: string }) {
  const today = localToday();
  // 고친 체크만 기억한다(나머지는 묶음 기본값) — 캐시로 먼저 보인 미리보기가 새로 와도 어긋나지 않게
  const [toggled, setToggled] = useState<Record<string, boolean>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const isOn = (row: MealShoppingRow, bucket: "buy" | "manual") => toggled[`${bucket}:${row.name}`] ?? bucket === "buy";
  const picked = [...data.buy.filter((r) => isOn(r, "buy")), ...data.manual.filter((r) => isOn(r, "manual"))];

  const add = async () => {
    if (busy) return;
    // ponytail: 온라인에서만 담는다(ShoppingAddButton과 같음 — 이미 목록에 있는 이름은 서버가 건너뛴다)
    if (!navigator.onLine) {
      setError(OFFLINE);
      return;
    }
    setBusy(true);
    setError("");
    let created = 0;
    const skipped: string[] = [];
    try {
      for (let i = 0; i < picked.length; i += BULK_MAX) {
        const res = await addMany(
          "meal_plan",
          picked.slice(i, i + BULK_MAX).map((r) => ({ name: cut(r.name, 50), quantity: r.quantity, unit: r.unit, planned_on: r.planned_on })),
          planName ? cut(planName, 60) : undefined,
        );
        created += res.created;
        skipped.push(...res.skipped);
      }
      forgetResources(url); // 다시 열면 담은 것이 `목록에 있어요`로
      const skippedText = addedText(0, skipped); // 뺀 것만
      showShoppingNotice(created ? `식단에서 ${created}개를 담았어요${skippedText ? ` · ${skippedText}` : ""}` : skippedText);
      navigate("/shopping", { replace: true });
    } catch (e) {
      const text = e instanceof ApiError && e.status === 0 ? OFFLINE : (e as Error).message;
      setError(created ? `${created}개는 담았어요 · ${text}` : text);
      if (created) forgetResources(url);
      setBusy(false);
    }
  };

  const group = (title: string, rows: MealShoppingRow[], render: (row: MealShoppingRow) => ReactNode) =>
    rows.length > 0 && (
      <section>
        <h2 className="sh-group ml-pgroup">
          <span>{title}</span>
          <span className="sr-only">, </span>
          <small>{rows.length}개</small>
        </h2>
        <div className="list">{rows.map(render)}</div>
      </section>
    );

  const checkRow = (bucket: "buy" | "manual") => (row: MealShoppingRow) => {
    const on = isOn(row, bucket);
    const amount = quantityText(row.quantity, row.unit);
    // 행 어디를 눌러도 체크가 바뀐다(체크 버튼 클릭도 여기로 올라온다). 스크린리더·키보드는 체크 버튼 하나로 다룬다
    return (
      <div key={row.name} className={on ? "ml-prow" : "ml-prow off"} onClick={() => setToggled({ ...toggled, [`${bucket}:${row.name}`]: !on })}>
        <button type="button" className="sh-check" role="checkbox" aria-checked={on} aria-label={`${row.name} ${amount} 담기`}>
          <i>{on && <Icon name="check" size={18} />}</i>
        </button>
        <span className="row-main">
          <span className="ml-pline">
            <span className="ml-title">{row.name}</span>
            <span className="ml-take">{bucket === "buy" ? `${amount} 담기` : amount}</span>
          </span>
          <span className="row-sub">{previewDetail(row)}</span>
          <span className="sh-meta">
            <span className="sh-tag">{buyDayText(row.planned_on, today)}</span>
            <span className="sh-tag info">식단</span>
          </span>
        </span>
      </div>
    );
  };

  return (
    <>
      <p className="r3-note">
        <Icon name="info" size={16} />
        <span>칸마다 인분에 맞춰 필요한 양을 계산하고, 재고에 있는 만큼 뺐어요. 살 날은 그 끼니 전날이에요.</span>
      </p>
      {group("모자란 만큼 담아요", data.buy, checkRow("buy"))}
      {group("단위가 달라요 · 직접 골라주세요", data.manual, checkRow("manual"))}
      {group("담지 않아요", data.skip, (row) => (
        <div key={row.name} className="ml-prow skip">
          <span className="row-main">
            <span className="ml-pline">
              <span className="ml-title">{row.name}</span>
              <span className="ml-take">{row.reason === "listed" ? "목록에 있어요" : "충분해요"}</span>
            </span>
            <span className="row-sub">{previewDetail(row)}</span>
          </span>
        </div>
      ))}
      <div className="cta-bar">
        {error && (
          <p className="error ml-cta-error" role="alert">
            {error}
          </p>
        )}
        <div className="actions">
          <button type="button" className="btn outline" disabled={busy} onClick={() => goBack("/meals")}>
            취소
          </button>
          <button type="button" className="btn primary" disabled={picked.length === 0 || busy} onClick={add}>
            {busy ? "담는 중…" : `${picked.length}개 장보기에 담기`}
          </button>
        </div>
      </div>
    </>
  );
}

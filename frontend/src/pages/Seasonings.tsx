import Icon from "../components/Icon";
import { SEASONING_PRESETS } from "../data/seasoningPresets";
import { basisLabel, type Seasoning } from "../seasoning";
import { navigate } from "../useHashRoute";
import { useResource } from "../useResource";

function SeasoningRows({ items, pathOf }: { items: Seasoning[]; pathOf: (s: Seasoning) => string }) {
  return (
    <ul className="list">
      {items.map((s) => (
        <li key={s.id}>
          <a
            className="row-btn"
            href={`#${pathOf(s)}`}
            onClick={(e) => {
              e.preventDefault();
              navigate(pathOf(s));
            }}
          >
            <span className="row-main">
              <span className="row-title">{s.name}</span>
              <span className="row-sub">
                {basisLabel(s)} · 재료 {s.items.length}개
              </span>
            </span>
            <Icon name="chevron" />
          </a>
        </li>
      ))}
    </ul>
  );
}

/** 레시피 탭의 `양념 비율` 칸: 내 비율(있을 때만) 위, 기본 양념 아래 (시안 SeasoningList) */
export default function Seasonings() {
  const { data, error, reload } = useResource<{ items: Seasoning[] }>("/api/seasonings");
  const mine = data?.items ?? [];

  return (
    <>
      {error && !data && (
        <div className="list-end">
          <p className="error" role="alert">
            {error}
          </p>
          <button className="btn secondary inline" onClick={reload}>
            <Icon name="refresh" size={16} />
            다시 불러오기
          </button>
        </div>
      )}
      {/* 내 비율이 뒤늦게 위에 끼어들어 기본 양념이 밀리지 않게, 처음 받을 때는 기다린다(다음부터는 캐시로 바로) */}
      {!data && !error && <p className="center muted">불러오는 중…</p>}
      {mine.length > 0 && (
        <section aria-labelledby="seasonings-mine">
          <h2 className="r3-sechead" id="seasonings-mine">
            내 비율
          </h2>
          <SeasoningRows items={mine} pathOf={(s) => `/recipes/seasonings/${s.id}`} />
        </section>
      )}
      {(data || error) && (
        <section aria-labelledby="seasonings-default">
          <h2 className="r3-sechead" id="seasonings-default">
            기본 양념
          </h2>
          <SeasoningRows items={SEASONING_PRESETS} pathOf={(s) => `/recipes/seasonings/preset/${s.id}`} />
        </section>
      )}
      <div className="cta-bar">
        <button className="btn primary" onClick={() => navigate("/recipes/seasonings/new")}>
          <Icon name="plus" />내 비율 만들기
        </button>
      </div>
    </>
  );
}

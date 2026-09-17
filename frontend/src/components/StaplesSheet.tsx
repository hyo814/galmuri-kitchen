import { useRef, useState, type FormEvent } from "react";
import { api, type Staple } from "../api";
import { withJosa } from "../format";
import { useAsyncAction } from "../useAsyncAction";
import Icon from "./Icon";
import ShoppingAddButton from "./ShoppingAddButton";
import Sheet from "./Sheet";

const CATEGORIES = ["조미료", "야채", "기타"];

interface Props {
  staples: Staple[];
  initialMissingOnly?: boolean;
  onChanged: () => Promise<unknown>;
  /** 없으면(더보기에서 연 경우) 떨어진 필수품을 눌러 재료를 추가하지 않고 표시만 한다 */
  onAddIngredient?: (name: string) => void;
  onClose: () => void;
}

export default function StaplesSheet({ staples, initialMissingOnly = false, onChanged, onAddIngredient, onClose }: Props) {
  const [editMode, setEditMode] = useState(false);
  const [missingOnly, setMissingOnly] = useState(initialMissingOnly);
  const [name, setName] = useState("");
  const [category, setCategory] = useState(CATEGORIES[0]);
  const nameRef = useRef<HTMLInputElement>(null);
  const { busy, error, run } = useAsyncAction();

  // 사용자가 직접 만든 분류(소스, 육류 등)도 칩과 그룹으로 보여 준다 (사용성 점검 C18)
  const categories = [...CATEGORIES, ...new Set(staples.map((s) => s.category).filter((c) => !CATEGORIES.includes(c)))];
  // 가졌던 것만 배너에(2026-09-17): "떨어진 것만"은 missing만(한 번도 없던 unstocked는 빼고 전체에서만 보인다)
  const missingCount = staples.filter((s) => s.status === "missing").length;
  const shown = missingOnly ? staples.filter((s) => s.status === "missing") : staples;
  const groups = categories
    .map((c) => ({ category: c, items: shown.filter((s) => s.category === c) }))
    .filter((g) => g.items.length > 0);

  // 추가 폼을 위로 올리고, 추가 후 입력칸에 포커스를 되돌린다 (사용성 점검 C5)
  const add = async (e: FormEvent) => {
    e.preventDefault();
    const ok = await run(async () => {
      await api("/api/staples", { method: "POST", body: { name, category } });
      await onChanged();
    });
    if (ok) {
      setName("");
      nameRef.current?.focus();
    }
  };

  const remove = (staple: Staple) => {
    if (!confirm(`${withJosa(staple.name, "을", "를")} 필수품에서 뺄까요?`)) return;
    run(async () => {
      await api(`/api/staples/${staple.id}`, { method: "DELETE" });
      await onChanged();
    });
  };

  return (
    <Sheet
      title="필수품"
      description="항상 있어야 하는 재료예요. 떨어지면 재고 화면에서 알려드려요."
      action={
        staples.length > 0 && (
          <button className="text-btn strong" onClick={() => setEditMode(!editMode)}>
            {editMode ? "완료" : "편집"}
          </button>
        )
      }
      onClose={onClose}
    >
      <form className="form compact" onSubmit={add}>
        <div className="add-row">
          <input
            ref={nameRef}
            className="input"
            id="new-staple-name"
            aria-label="필수품 이름"
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={50}
            placeholder="예: 고춧가루"
            required
          />
          <button className="btn primary" disabled={busy}>
            추가
          </button>
        </div>
        <div className="choices" role="group" aria-label="분류">
          {categories.map((c) => (
            <button key={c} type="button" className="choice" aria-pressed={category === c} onClick={() => setCategory(c)}>
              {c}
            </button>
          ))}
        </div>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
      </form>

      {staples.length > 0 && (
        <div className="choices divider-top" role="group" aria-label="보기">
          <button type="button" className="choice" aria-pressed={!missingOnly} onClick={() => setMissingOnly(false)}>
            전체 {staples.length}
          </button>
          <button type="button" className="choice" aria-pressed={missingOnly} onClick={() => setMissingOnly(true)}>
            떨어진 것만 {missingCount}
          </button>
        </div>
      )}

      {groups.length === 0 ? (
        <p className="hint">{staples.length === 0 ? "아직 등록한 필수품이 없어요. 위에서 추가해 보세요." : "떨어진 필수품이 없어요."}</p>
      ) : (
        <div className="groups">
          {groups.map((group) => (
            <section key={group.category} className="group" aria-label={group.category}>
              <h3 className="section-label">{group.category}</h3>
              <ul className="plain-list">
                {group.items.map((staple) => (
                  <li key={staple.id}>
                    {editMode ? (
                      <div className="plain-row">
                        <span className="staple-name">{staple.name}</span>
                        <button className="btn danger-text inline" disabled={busy} onClick={() => remove(staple)}>
                          삭제
                        </button>
                      </div>
                    ) : staple.status === "in_stock" ? (
                      <div className="plain-row">
                        <span className="staple-name">{staple.name}</span>
                        <span className="stock-ok">
                          <Icon name="check" size={16} />
                          있어요
                          {staple.matched_name && staple.matched_name !== staple.name && ` · ${staple.matched_name}`}
                        </span>
                      </div>
                    ) : staple.status === "unstocked" ? (
                      // 한 번도 재고에 없던 필수품 — 배너·장보기에는 안 뜨고 시트에만 보인다 (2026-09-17)
                      <div className="plain-row">
                        <span className="staple-name">{staple.name}</span>
                        <span className="badge">없어요</span>
                      </div>
                    ) : !onAddIngredient ? (
                      <div className="plain-row">
                        <span className="staple-name">{staple.name}</span>
                        <span className="badge danger">떨어짐</span>
                      </div>
                    ) : (
                      // 떨어진 필수품을 누르면 이름이 채워진 재료 추가가 열린다 (사용성 점검 C6)
                      <button
                        className="plain-row row-press"
                        aria-label={`${staple.name} 떨어짐, 재고에 추가`}
                        onClick={() => onAddIngredient(staple.name)}
                      >
                        <span className="staple-name">{staple.name}</span>
                        <span className="row-end">
                          <span className="badge danger">떨어짐</span>
                          <span className="add-hint">추가</span>
                        </span>
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      )}

      {!editMode && missingCount > 0 && (
        <ShoppingAddButton
          source="staple"
          items={staples.filter((s) => s.status === "missing").map((s) => ({ name: s.name }))}
          label={`떨어진 필수품 ${missingCount}개 장보기에 담기`}
        />
      )}
    </Sheet>
  );
}

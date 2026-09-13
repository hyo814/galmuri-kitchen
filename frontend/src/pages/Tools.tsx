import { useState } from "react";
import { api, type KitchenTool, type KitchenToolInput } from "../api";
import Icon from "../components/Icon";
import ToolForm from "../components/ToolForm";
import { cycleLabel, formatDate, withJosa } from "../format";
import { goBack } from "../useHashRoute";
import { useResource } from "../useResource";

function subtitle(tool: KitchenTool): string {
  const parts: string[] = [tool.category];
  if (tool.check_every_months) parts.push(`${cycleLabel(tool.check_every_months)}마다 점검`);
  if (tool.last_checked_on) parts.push(`마지막 점검 ${formatDate(tool.last_checked_on)}`);
  else if (tool.bought_on) parts.push(`${formatDate(tool.bought_on)} 구매`);
  return parts.join(" · ");
}

export default function Tools() {
  const { data: tools, error, reload: load } = useResource<KitchenTool[]>("/api/tools");
  const [editing, setEditing] = useState<KitchenTool | "new" | null>(null);

  // 오류는 던져서 시트 안에 표시한다.
  const save = async (input: KitchenToolInput) => {
    if (editing === "new") await api("/api/tools", { method: "POST", body: input });
    else if (editing) await api(`/api/tools/${editing.id}`, { method: "PATCH", body: input });
    setEditing(null);
    await load();
  };

  const mark = (action: "checked" | "replaced") => async () => {
    if (!editing || editing === "new") return;
    await api(`/api/tools/${editing.id}/${action}`, { method: "POST" });
    setEditing(null);
    await load();
  };

  const remove = async () => {
    if (!editing || editing === "new" || !confirm(`${withJosa(editing.name, "을", "를")} 삭제할까요?`)) return;
    await api(`/api/tools/${editing.id}`, { method: "DELETE" });
    setEditing(null);
    await load();
  };

  const due = tools?.filter((t) => t.is_due).length ?? 0;

  return (
    <main className="page">
      <a
        className="back-link"
        href="#/more"
        onClick={(e) => {
          e.preventDefault();
          goBack("/more");
        }}
      >
        <Icon name="back" size={18} />
        더보기
      </a>
      <header className="topbar">
        <div>
          <h1>주방 도구</h1>
          {tools && tools.length > 0 && (
            <p className="summary">
              도구 {tools.length}개{due > 0 && ` · 점검할 도구 ${due}개`}
            </p>
          )}
        </div>
      </header>

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}

      {tools === undefined ? (
        !error && <p className="center muted">불러오는 중…</p>
      ) : tools.length === 0 ? (
        <div className="empty">
          <p>등록한 도구가 없어요.</p>
          <p className="muted">프라이팬, 뒤집개처럼 자주 쓰는 도구를 추가해 보세요.</p>
        </div>
      ) : (
        <ul className="list">
          {tools.map((tool) => (
            <li key={tool.id}>
              <button className="row-btn" onClick={() => setEditing(tool)}>
                <span className="row-main">
                  <span className="row-title">{tool.name}</span>
                  <span className="row-sub">{subtitle(tool)}</span>
                </span>
                {tool.is_due ? (
                  <span className="badge old">점검할 때</span>
                ) : (
                  tool.days_until_due !== null &&
                  tool.days_until_due <= 14 && <span className="badge">D-{tool.days_until_due}</span>
                )}
              </button>
            </li>
          ))}
        </ul>
      )}

      <div className="cta-bar">
        <button className="btn primary" onClick={() => setEditing("new")}>
          <Icon name="plus" />
          도구 추가
        </button>
      </div>

      {editing && (
        <ToolForm
          initial={editing === "new" ? null : editing}
          onSubmit={save}
          onChecked={editing === "new" ? undefined : mark("checked")}
          onReplaced={editing === "new" ? undefined : mark("replaced")}
          onDelete={editing === "new" ? undefined : remove}
          onClose={() => setEditing(null)}
        />
      )}
    </main>
  );
}

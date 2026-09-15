// 장보기 메모 사진에서 살 것 뽑기(4단계 계획 Task 11). 확인 화면 시안이 없어 재고 스캔 확인(ScanReview)을 구입일·가격 없이 따른다.
import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { ApiError, type LocationKind, type ScanResult, type StorageLocation } from "../api";
import { MEMO_SCAN_CHECK_MAX, memoScanRows, parseQuantityText, plannedOnFor, quantityText } from "../shopping/sync";
import { addMany } from "../shopping/useShopping";
import { useAsyncAction } from "../useAsyncAction";
import { useResource } from "../useResource";
import Icon from "./Icon";
import { ScanFail, ScanWait, uploadScan, useStepFocus } from "./ScanSheet";
import Sheet from "./Sheet";
import { addedText } from "./ShoppingAddButton";

const OFFLINE = "인터넷이 연결되면 담을 수 있어요";
const WHEN_CHIPS = [["today", "오늘"], ["week", "이번 주"], ["undated", "날짜 미정"]] as const;

type Step =
  | { name: "loading" }
  | { name: "review"; result: ScanResult }
  | { name: "error"; message: string; status: number; reason?: "empty" };

interface Props {
  image: Blob;
  /** 장보기 항목 출처 이름: 메모의 어디서, 없으면 `장보기 메모` */
  sourceLabel: string;
  /** 지금 장보기 목록의 이름들(이미 있는 건 끈 채로 `목록에 있어요`) */
  listed: string[];
  today: string;
  /** 인식 요청이 끝났다(남은 횟수 새로 받기) */
  onScanned: () => void;
  onDone: (text: string) => void;
  onClose: () => void;
}

export default function MemoScanReview({ image, sourceLabel, listed, today, onScanned, onDone, onClose }: Props) {
  const [step, setStep] = useState<Step>({ name: "loading" });
  const rootRef = useRef<HTMLDivElement>(null);
  useStepFocus(rootRef, step.name);

  // 닫으면(뒤로가기·배경 탭·취소) 진행 중인 인식 요청도 멈춘다
  useEffect(() => {
    const controller = new AbortController();
    uploadScan("memo", [image], controller.signal).then(
      (result) => {
        onScanned();
        setStep(result.items.length ? { name: "review", result } : { name: "error", message: "사진에서 살 것을 찾지 못했어요.", status: 0, reason: "empty" });
      },
      (e) => {
        if (controller.signal.aborted) return;
        onScanned();
        setStep({ name: "error", message: (e as Error).message, status: e instanceof ApiError ? e.status : 0 });
      },
    );
    return () => controller.abort();
  }, [image]); // eslint-disable-line react-hooks/exhaustive-deps

  const liveText =
    step.name === "loading" ? "사진에서 살 것을 찾고 있어요" : step.name === "review" ? `살 것 ${step.result.items.length}개를 찾았어요` : step.message;

  const sheetProps =
    step.name === "review"
      ? { title: `찾은 살 것 ${step.result.items.length}개`, description: "담을 것만 체크해주세요", className: "scan-tall" }
      : { title: step.name === "loading" ? "살 것을 찾는 중" : "인식 실패", hideHeader: true };

  return (
    <div ref={rootRef}>
      <Sheet {...sheetProps} onClose={onClose}>
        <p className="sr-only" role="status" aria-live="polite">
          {liveText}
        </p>
        {step.name === "loading" && <ScanWait title="사진에서 살 것을 찾고 있어요…" photo="메모 사진 1장" onCancel={onClose} />}
        {step.name === "review" && <Review result={step.result} sourceLabel={sourceLabel} listed={listed} today={today} onDone={onDone} />}
        {step.name === "error" && (
          <>
            <ScanFail message={step.message} status={step.status} reason={step.reason} />
            <button type="button" className="btn secondary" onClick={onClose}>
              닫기
            </button>
          </>
        )}
      </Sheet>
    </div>
  );
}

interface Row {
  key: number;
  checked: boolean;
  listed: boolean;
  name: string;
  quantity: string;
  household: boolean;
  locationKind: LocationKind;
}

function Review({ result, sourceLabel, listed, today, onDone }: Pick<Props, "sourceLabel" | "listed" | "today" | "onDone"> & { result: ScanResult }) {
  const [rows, setRows] = useState<Row[]>(() => {
    const first = memoScanRows(result.items.map((i) => i.name), listed);
    return result.items.map((item, key) => ({
      key,
      ...first[key],
      name: item.name,
      quantity: quantityText(item.quantity, item.unit),
      household: !!item.household,
      locationKind: item.location_kind,
    }));
  });
  const [openKey, setOpenKey] = useState<number | null>(null);
  const [when, setWhen] = useState<(typeof WHEN_CHIPS)[number][0]>("today");
  const { busy, error, setError, run } = useAsyncAction();
  // 넣을 곳은 화면에 보이지 않게 AI가 짐작한 보관 종류의 첫 위치로 채운다(재고에 넣기 화면 프리필). 못 받으면 비워 둔다
  const { data: locations } = useResource<StorageLocation[]>("/api/locations");
  const whenLabel = useId();

  const chosen = rows.filter((r) => r.checked);
  const allOn = chosen.length === rows.length;
  const update = (key: number, patch: Partial<Row>) => setRows((prev) => prev.map((r) => (r.key === key ? { ...r, ...patch } : r)));

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const bad = chosen.find((r) => !r.name.trim() || !parseQuantityText(r.quantity));
    if (bad) {
      setOpenKey(bad.key);
      setError("이름을 채우고 수량은 1모, 30구처럼 입력해주세요.");
      return;
    }
    if (!navigator.onLine) {
      setError(OFFLINE);
      return;
    }
    run(async () => {
      const planned_on = plannedOnFor(when, today);
      const items = chosen.map((r) => ({
        name: r.name.trim(),
        ...parseQuantityText(r.quantity)!,
        planned_on,
        household: r.household,
        location_id: locations?.find((l) => l.kind === r.locationKind)?.id,
      }));
      try {
        const res = await addMany("memo", items, sourceLabel);
        onDone(addedText(res.created, res.skipped));
      } catch (e) {
        const first = e instanceof ApiError ? e.errors?.[0] : undefined;
        const row = first && chosen[first.index];
        if (row) {
          setOpenKey(row.key);
          throw new Error(first.error);
        }
        throw e instanceof ApiError && e.status === 0 ? new Error(OFFLINE) : e;
      }
    });
  };

  return (
    <form className="form scan-review" onSubmit={submit}>
      {result.sample && (
        <span className="badge info scan-sample">
          <Icon name="info" size={16} />
          예시 결과예요 · 사진을 읽지 않았어요
        </span>
      )}

      {rows.length > MEMO_SCAN_CHECK_MAX && (
        <button
          type="button"
          className="btn secondary inline mo-scan-all"
          onClick={() => setRows((prev) => prev.map((r) => ({ ...r, checked: !allOn })))}
        >
          {allOn ? "모두 해제" : "모두 선택"}
        </button>
      )}

      <ul className="scan-items">
        {rows.map((row) => {
          const open = openKey === row.key;
          const toggle = () => setOpenKey(open ? null : row.key);
          const editId = `memo-scan-edit-${row.key}`;
          return (
            <li key={row.key} className={`scan-item${row.checked ? "" : " off"}${open ? " open" : ""}`}>
              <button
                type="button"
                className={`checkbox${row.checked ? "" : " off"}`}
                role="checkbox"
                aria-checked={row.checked}
                aria-label={`${row.name || "살 것"} 담기`}
                onClick={() => update(row.key, { checked: !row.checked })}
              >
                <span>{row.checked && <Icon name="check" size={16} />}</span>
              </button>
              {open ? (
                <input className="input" aria-label="이름" value={row.name} maxLength={50} onChange={(e) => update(row.key, { name: e.target.value })} />
              ) : (
                <button type="button" className="row-main scan-item-main" aria-expanded={open} aria-controls={editId} onClick={toggle}>
                  <span className="row-title">
                    {row.name}
                    {row.household && <span className="badge sh-in-tag mo-scan-tag">생활용품</span>}
                  </span>
                  <span className="row-sub">
                    {row.quantity}
                    {row.listed && " · 목록에 있어요"}
                  </span>
                </button>
              )}
              <button
                type="button"
                className="icon-btn"
                aria-label={open ? "접기" : `${row.name} 고치기`}
                aria-expanded={open}
                aria-controls={editId}
                onClick={toggle}
              >
                <Icon name={open ? "up" : "down"} />
              </button>
              {open && (
                <div className="scan-edit mo-scan-edit" id={editId}>
                  <label className="field">
                    <span className="field-label">수량</span>
                    <input
                      className="input"
                      value={row.quantity}
                      placeholder="1개"
                      maxLength={20}
                      onChange={(e) => update(row.key, { quantity: e.target.value })}
                    />
                  </label>
                  <span className="sh-in-toggle">
                    <span aria-hidden="true">생활용품</span>
                    <button
                      type="button"
                      role="switch"
                      aria-checked={row.household}
                      aria-label={`${row.name || "살 것"} 생활용품`}
                      className="r3-toggle"
                      onClick={() => update(row.key, { household: !row.household })}
                    />
                  </span>
                </div>
              )}
            </li>
          );
        })}
      </ul>

      <div className="field">
        <span className="field-label" id={whenLabel}>
          언제 살까요?
        </span>
        <div className="sh-when" role="group" aria-labelledby={whenLabel}>
          {WHEN_CHIPS.map(([key, label]) => (
            <button key={key} type="button" aria-pressed={when === key} onClick={() => setWhen(key)}>
              {label}
            </button>
          ))}
        </div>
      </div>

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}

      <div className="scan-foot">
        <button className="btn primary" disabled={busy || chosen.length === 0}>
          {busy ? "담는 중…" : `${chosen.length}개 장보기에 담기`}
        </button>
      </div>
    </form>
  );
}

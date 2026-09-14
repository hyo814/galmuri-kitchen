import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import type { User } from "../api";
import { formatDate, withJosa } from "../format";
import { nameKey, plannedOnFor, parseQuantityText, quantityText, type EditFields, type ViewItem } from "../shopping/sync";
import { setLeaveGuard } from "../useHashRoute";
import Icon from "./Icon";
import Sheet from "./Sheet";

type When = "today" | "week" | "undated" | "date";
const WHEN_CHIPS: [Exclude<When, "date">, string][] = [["today", "오늘"], ["week", "이번 주"], ["undated", "날짜 미정"]];

export interface ItemInput { name: string; quantity: number; unit: string; planned_on: string | null }

interface Props {
  /** 없으면 살 것 추가, 있으면 고치기 */
  item?: ViewItem;
  today: string;
  /** 추가: 모든 칸 / 고치기: 바뀐 칸만 */
  onSave: (fields: ItemInput | EditFields, keepOpen: boolean) => void;
  /** 추가: 지금 목록 이름들(같은 이름이면 한 번 알리고 `그래도 담기`로 담는다) */
  listedNames?: string[];
  onDelete?: () => void;
  onClose: () => void;
  user: User;
  offline: boolean;
  /** 추가 모드의 "사진에서 뽑기": 이 시트를 닫고 사진 고르기를 연다 */
  onScanPhoto: () => void;
}

function whenOf(plannedOn: string | null, today: string): { when: When; date: string } {
  if (plannedOn === null) return { when: "undated", date: "" };
  if (plannedOn <= today) return { when: "today", date: "" };
  if (plannedOn === plannedOnFor("week", today)) return { when: "week", date: "" };
  return { when: "date", date: plannedOn };
}

/** 시안 AddSheet: 살 것 추가·고치기. 저장은 useShopping.act라 인터넷이 없어도 된다 */
export default function ShoppingItemSheet({ item, today, onSave, listedNames = [], onDelete, onClose, user, offline, onScanPhoto }: Props) {
  const initial = item ? whenOf(item.planned_on, today) : { when: "today" as When, date: "" };
  const startQuantity = item ? quantityText(item.quantity, item.unit) : "";
  const [name, setName] = useState(item?.name ?? "");
  const [quantity, setQuantity] = useState(startQuantity);
  const [when, setWhen] = useState<When>(initial.when);
  const [date, setDate] = useState(initial.date);
  const [added, setAdded] = useState("");
  /** 목록에 이미 있는 이름으로 추가하려 할 때 알림(이름을 바꾸면 사라진다) */
  const [dup, setDup] = useState<{ name: string; keepOpen: boolean } | null>(null);
  /** 수량 칸을 떠났거나 저장을 눌렀을 때만 틀렸다고 보여준다 */
  const [touched, setTouched] = useState(false);
  /** showPicker가 없는 브라우저: 날짜 칸을 보이게 해서 직접 고르게 한다 */
  const [dateVisible, setDateVisible] = useState(false);
  const [scanHint, setScanHint] = useState("");
  const nameRef = useRef<HTMLInputElement>(null);
  const dateRef = useRef<HTMLInputElement>(null);
  const whenLabel = useId();
  const quantityError = useId();

  const parsed = parseQuantityText(quantity);
  const showQuantityError = touched && !parsed;
  const dirty = name !== (item?.name ?? "") || quantity !== startQuantity || when !== initial.when || date !== initial.date;
  const canSave = name.trim() !== "" && parsed !== null;

  // 작성 중에 탭을 옮기면 묻는다
  const dirtyRef = useRef(dirty);
  dirtyRef.current = dirty;
  useEffect(() => {
    setLeaveGuard(() => !dirtyRef.current || confirm("작성 중인 내용이 사라져요. 나갈까요?"));
    return () => setLeaveGuard(null);
  }, []);

  const plannedOn = () => {
    if (when === "date") return date;
    // 고치기에서 칩을 안 바꿨으면 원래 날짜 그대로(지난 날짜를 오늘로 바꾸지 않게)
    if (item && when === initial.when) return item.planned_on;
    return plannedOnFor(when, today);
  };

  useEffect(() => {
    if (dateVisible) dateRef.current?.focus();
  }, [dateVisible]);

  const save = (keepOpen: boolean, anyway = false) => {
    if (!canSave || !parsed) {
      setTouched(true);
      return;
    }
    const fields: ItemInput = { name: name.trim(), ...parsed, planned_on: plannedOn() };
    if (!item) {
      if (!anyway && listedNames.some((n) => nameKey(n) === nameKey(fields.name))) {
        setDup({ name: fields.name, keepOpen });
        return;
      }
      setDup(null);
      onSave(fields, keepOpen);
      if (!keepOpen) return;
      // 이름·수량만 비우고 언제 살까요는 그대로
      setName("");
      setQuantity("");
      setTouched(false);
      setAdded(fields.name);
      nameRef.current?.focus();
      return;
    }
    const changed: EditFields = {};
    if (fields.name !== item.name) changed.name = fields.name;
    if (fields.quantity !== item.quantity) changed.quantity = fields.quantity;
    if (fields.unit !== item.unit) changed.unit = fields.unit;
    if (fields.planned_on !== item.planned_on) changed.planned_on = fields.planned_on;
    onSave(changed, false);
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    save(false);
  };

  const openDatePicker = () => {
    const input = dateRef.current;
    if (!input) return;
    try {
      input.showPicker();
    } catch {
      setDateVisible(true); // showPicker가 없는 브라우저: 보이는 날짜 칸으로 바꾸고 포커스
    }
  };

  return (
    <Sheet title={item ? "살 것 고치기" : "살 것 추가"} focusTitle={!!item} onClose={onClose}>
      <form className="sh-form" onSubmit={submit}>
        <p className="sr-only" role="status">
          {added && `${withJosa(added, "을", "를")} 담았어요`}
        </p>
        <div className="sh-two">
          <label className="field">
            <span className="field-label">이름</span>
            <input
              ref={nameRef}
              className="input"
              value={name}
              onChange={(e) => {
                setName(e.target.value);
                setDup(null);
              }}
              maxLength={50}
              enterKeyHint="done"
              autoFocus={!item}
            />
          </label>
          <label className="field">
            <span className="field-label">수량</span>
            <input
              className={showQuantityError ? "input invalid" : "input"}
              value={quantity}
              onChange={(e) => setQuantity(e.target.value)}
              onBlur={() => setTouched(true)}
              placeholder="1개"
              maxLength={20}
              aria-invalid={showQuantityError}
              aria-describedby={showQuantityError ? quantityError : undefined}
            />
          </label>
        </div>
        {dup && (
          <p className="notice sh-dup" role="status">
            <span>{withJosa(dup.name, "은", "는")} 이미 목록에 있어요</span>
            <button type="button" className="r3-link" onClick={() => save(dup.keepOpen, true)}>
              그래도 담기
            </button>
          </p>
        )}
        {showQuantityError && (
          <p id={quantityError} className="rc-err">
            수량을 1모, 30구처럼 입력해주세요
          </p>
        )}
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
            <button type="button" aria-pressed={when === "date"} onClick={openDatePicker}>
              <Icon name="calendar" size={16} />
              {when === "date" && date ? formatDate(date) : "날짜 고르기"}
            </button>
            <input
              ref={dateRef}
              className={dateVisible ? "input" : "sr-only"}
              type="date"
              tabIndex={dateVisible ? undefined : -1}
              aria-hidden={dateVisible ? undefined : true}
              aria-label="날짜 고르기"
              min={today}
              value={date}
              onChange={(e) => {
                if (!e.target.value) return;
                setDate(e.target.value);
                setWhen("date");
              }}
            />
          </div>
        </div>
        {item ? (
          <>
            <button className="btn primary" disabled={!canSave}>
              저장
            </button>
            {onDelete && (
              <button
                type="button"
                className="btn danger-text"
                onClick={() => {
                  if (confirm("목록에서 뺄까요?")) onDelete();
                }}
              >
                목록에서 빼기
              </button>
            )}
          </>
        ) : (
          <div className="actions">
            <button type="button" className="btn outline" disabled={!canSave} onClick={() => save(true)}>
              계속 추가
            </button>
            <button className="btn primary" disabled={!canSave}>
              추가
            </button>
          </div>
        )}
        {!item && user.scan !== "off" && (
          <>
            <button
              type="button"
              className="r3-link"
              onClick={() => {
                if (offline) { setScanHint("인터넷이 연결되면 읽을 수 있어요"); return; }
                onScanPhoto();
              }}
            >
              <Icon name="sparkle" size={16} />
              사진에서 뽑기
            </button>
            {scanHint && (
              <p className="rc-err sh-ai-hint" role="status">
                {scanHint}
              </p>
            )}
          </>
        )}
      </form>
    </Sheet>
  );
}

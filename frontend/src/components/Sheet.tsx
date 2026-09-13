import { useEffect, useId, useRef, type ReactNode } from "react";

interface Props {
  title: string;
  description?: string;
  action?: ReactNode;
  /** 시트 크기·모양 변형(예: "scan-tall") */
  className?: string;
  /** 제목을 화면에서 숨기고 스크린리더에만 읽힌다(로딩·실패 화면처럼 본문이 제목을 대신할 때) */
  hideHeader?: boolean;
  onClose: () => void;
  children: ReactNode;
}

/** 네이티브 <dialog> 바텀시트. Esc·안드로이드 뒤로가기·배경 탭으로 닫힌다. */
export default function Sheet({ title, description, action, className, hideHeader, onClose, children }: Props) {
  const ref = useRef<HTMLDialogElement>(null);
  const pointerDownOnDialog = useRef(false);
  const titleId = useId();

  useEffect(() => {
    const dialog = ref.current;
    if (dialog && !dialog.open) dialog.showModal(); // StrictMode 이중 실행 대비
    // 언마운트 시 close()를 호출하지 않는다: StrictMode는 mount → cleanup → mount로
    // 두 번 실행하는데, cleanup에서 close()하면 그 close 이벤트가 onClose를 불러
    // 시트가 열리자마자 스스로 닫혀 버린다.
  }, []);

  return (
    <dialog
      ref={ref}
      className={className ? `sheet ${className}` : "sheet"}
      aria-labelledby={titleId}
      onClose={onClose}
      onPointerDown={(e) => {
        pointerDownOnDialog.current = e.target === e.currentTarget;
      }}
      onClick={(e) => {
        // 배경(::backdrop) 탭: 누르기 시작도 배경(다이얼로그 자신)이었을 때만 —
        // 입력창에서 배경으로 드래그해 놓는 동작은 닫지 않는다.
        if (e.target === e.currentTarget && pointerDownOnDialog.current) ref.current?.close();
      }}
    >
      <div className="sheet-body">
        <div className="sheet-handle" aria-hidden="true" />
        <div className={hideHeader ? "sheet-header sr-only" : "sheet-header"}>
          <div>
            <h2 id={titleId}>{title}</h2>
            {description && <p className="sheet-desc">{description}</p>}
          </div>
          {action}
        </div>
        {children}
      </div>
    </dialog>
  );
}

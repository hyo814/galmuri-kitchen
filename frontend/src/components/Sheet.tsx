import { useEffect, useId, useRef, type ReactNode } from "react";

interface Props {
  title: string;
  description?: string;
  action?: ReactNode;
  onClose: () => void;
  children: ReactNode;
}

/** 네이티브 <dialog> 바텀시트. Esc·안드로이드 뒤로가기·배경 탭으로 닫힌다. */
export default function Sheet({ title, description, action, onClose, children }: Props) {
  const ref = useRef<HTMLDialogElement>(null);
  const pointerDownOnDialog = useRef(false);
  const titleId = useId();

  useEffect(() => {
    const dialog = ref.current;
    if (dialog && !dialog.open) dialog.showModal(); // StrictMode 이중 실행 대비
    return () => {
      if (dialog?.open) dialog.close(); // 오프너로 포커스를 되돌린다 (네이티브 <dialog> 동작)
    };
  }, []);

  return (
    <dialog
      ref={ref}
      className="sheet"
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
        <div className="sheet-header">
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

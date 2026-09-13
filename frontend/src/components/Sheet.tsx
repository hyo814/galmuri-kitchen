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
  const titleId = useId();

  useEffect(() => {
    const dialog = ref.current;
    if (dialog && !dialog.open) dialog.showModal(); // StrictMode 이중 실행 대비
  }, []);

  return (
    <dialog
      ref={ref}
      className="sheet"
      aria-labelledby={titleId}
      onClose={onClose}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose(); // 배경(::backdrop) 탭
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

import Icon from "./Icon";

/** 불러오기 실패 공통 화면: 오류 문구 + 다시 불러오기 버튼 */
export default function LoadError({ error, onRetry }: { error: string; onRetry: () => void }) {
  return (
    <div className="list-end">
      <p className="error" role="alert">
        {error}
      </p>
      <button type="button" className="btn secondary inline" onClick={onRetry}>
        <Icon name="refresh" size={16} />
        다시 불러오기
      </button>
    </div>
  );
}

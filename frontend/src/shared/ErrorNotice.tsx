import { useEffect, useState } from 'react';
import { ApiError } from './api';
import styles from './ErrorNotice.module.css';

const actions: Record<string, string> = {
  fix_input: '请检查输入后重试',
  resolve_same_key: '请使用原请求标识找回结果',
  retry_later: '请稍后重试',
  login: '请重新登录',
  refresh: '请刷新页面后重试',
  retry_later_or_report: '请稍后重试，持续失败时提供 request ID 排查',
  none: '',
};

export function ErrorNotice({ error, handledFields = [] }: { error: Error | null; handledFields?: string[] }) {
  const [copyStatus, setCopyStatus] = useState('');
  useEffect(() => setCopyStatus(''), [error]);
  if (!error) return null;
  if (!(error instanceof ApiError)) {
    return <div className={styles.notice} role="alert">请求未完成，请检查连接后重试。</div>;
  }
  const body = error.body;
  const action = body.code === 'CSRF_REJECTED' ? '会话已重新获取，请刷新页面后重试。'
    : body.code === 'ORIGIN_REJECTED' ? '来源校验失败，请从管理入口地址访问。'
      : actions[body.action] ?? '';
  const retryAfter = [429, 503].includes(error.status) ? body.retry_after_seconds : null;
  return <div className={styles.notice} role="alert">
    <p>{body.message}</p>
    {action && <p>{action}</p>}
    {retryAfter != null && <p>请等待 {retryAfter} 秒后重试</p>}
    {body.details?.filter((detail) => !detail.field || !handledFields.includes(detail.field))
      .map((detail, index) => <p key={index}>{detail.message}</p>)}
    <div className={styles.request}>
      <span>request ID</span>
      <code>{body.request_id}</code>
      <button type="button" onClick={async () => {
        try {
          await navigator.clipboard.writeText(body.request_id);
          setCopyStatus('已复制');
        } catch {
          setCopyStatus('复制失败，请选择 request ID 手动复制');
        }
      }}>复制 request ID</button>
    </div>
    {copyStatus && <p role="status">{copyStatus}</p>}
  </div>;
}

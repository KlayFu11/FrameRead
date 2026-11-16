import { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router';
import { type AdminClient, type TaskSnapshot } from '../shared/api';
import { ErrorNotice } from '../shared/ErrorNotice';
import { isTerminalStatus, mergeTaskSnapshot } from './taskState';
import styles from './App.module.css';

const pollIntervalMs = 2_000;
const maxPollIntervalMs = 30_000;
const staleAfterMs = 10_000;

function statusLabel(status: string): string {
  const labels: Record<string, string> = {
    queued: '排队中', running: '运行中', retry_wait: '等待安全重试',
    cancel_requested: '取消中', succeeded: '已完成', failed: '处理失败', canceled: '已取消',
  };
  return labels[status] ?? status;
}

function errorMessage(snapshot: TaskSnapshot): string | null {
  if (!snapshot.error) return null;
  return snapshot.error.code === 'PIPELINE_NOT_AVAILABLE'
    ? 'S0 骨架不会生成文章，任务未进入真实解读流水线。'
    : snapshot.error.message;
}

export function TaskDetail({ api, taskId }: { api: AdminClient; taskId: string }) {
  const navigate = useNavigate();
  const [snapshot, setSnapshot] = useState<TaskSnapshot | null>(null);
  const [recovered, setRecovered] = useState(false);
  const [expired, setExpired] = useState(false);
  const [terminal, setTerminal] = useState(false);
  const pollFailures = useRef(0);
  const [clock, setClock] = useState(() => Date.now());
  const retiredEpochs = useRef<Set<string>>(new Set());
  const query = useQuery({
    queryKey: ['admin', 'task', taskId],
    queryFn: async () => {
      try {
        const result = await api.taskSnapshot(taskId);
        pollFailures.current = 0;
        return result;
      } catch (error) {
        pollFailures.current += 1;
        throw error;
      }
    },
    retry: false,
    refetchOnWindowFocus: false,
    refetchIntervalInBackground: false,
    refetchInterval: () => {
      if (terminal) return false;
      return Math.min(pollIntervalMs * (2 ** pollFailures.current), maxPollIntervalMs);
    },
  });

  useEffect(() => {
    if (!query.data) return;
    const result = mergeTaskSnapshot(snapshot, query.data, retiredEpochs.current);
    if (result.accepted) {
      if (snapshot && result.recovered) retiredEpochs.current.add(snapshot.instance_epoch);
      setSnapshot(result.snapshot);
      if (result.recovered) setRecovered(true);
      setTerminal(isTerminalStatus(result.snapshot.status));
    }
  }, [query.data, snapshot]);

  useEffect(() => {
    if (!query.isSuccess) return;
    setExpired(false);
  }, [query.dataUpdatedAt, query.isSuccess]);

  useEffect(() => {
    if (!query.error) return;
    setExpired(Boolean(snapshot));
  }, [query.error, snapshot]);

  useEffect(() => {
    if (!query.data) return;
    const remaining = query.dataUpdatedAt + staleAfterMs - Date.now();
    if (remaining <= 0) {
      setClock(Date.now());
      return;
    }
    const timeout = window.setTimeout(() => setClock(Date.now()), remaining);
    return () => window.clearTimeout(timeout);
  }, [query.dataUpdatedAt]);

  const lastSuccessfulSyncAt = query.data ? query.dataUpdatedAt : null;
  const syncIsStale = lastSuccessfulSyncAt !== null && clock - lastSuccessfulSyncAt >= staleAfterMs;
  const showExpired = expired || Boolean(query.error && snapshot);

  if (query.isPending && !snapshot) return <section className={styles.taskPage}><p role="status">正在读取任务快照…</p></section>;

  return <section className={styles.taskPage} aria-labelledby="task-detail-title">
    <div className={styles.pageHeading}>
      <div>
        <p className={styles.eyebrow}>任务详情</p>
        <h1 id="task-detail-title">视频任务</h1>
        <p className={styles.taskId}>任务 ID：<code>{taskId}</code></p>
      </div>
      <button className={styles.linkButton} type="button" onClick={() => void navigate('/manage/videos/new')}>提交新任务</button>
    </div>
    {recovered && <p className={styles.recovery} role="status">实例已恢复，已重新同步任务状态。</p>}
    {showExpired && <p className={styles.expired} role="status">连接中断，以下为最后一次成功同步的快照。</p>}
    {syncIsStale && <p className={styles.muted} role="status">上次成功同步：{new Date(lastSuccessfulSyncAt).toLocaleString()}</p>}
    {query.error && <ErrorNotice error={query.error} />}
    {snapshot && <>
      <div className={styles.statusCard}>
        <div>
          <span className={styles.statusLabel}>当前状态</span>
          <strong>{statusLabel(snapshot.status)}</strong>
        </div>
        <div className={styles.statusMeta}>阶段：{snapshot.stage ?? '尚未开始'}</div>
      </div>
      {snapshot.kind === 'video' && <aside className={styles.skeletonNotice}>
        <strong>S0 骨架：不会生成文章</strong>
        <p>当前切片只验证任务受理、排队和状态快照，尚未接入视频解读流水线。</p>
      </aside>}
      <dl className={styles.taskFacts}>
        <div><dt>任务截止时间</dt><dd>{new Date(snapshot.deadline_at).toLocaleString()}</dd></div>
        <div><dt>进度观察时间</dt><dd>{snapshot.progress ? new Date(snapshot.progress.observed_at).toLocaleString() : '暂无'}</dd></div>
      </dl>
      {errorMessage(snapshot) && <div className={styles.inlineError} role="alert">{errorMessage(snapshot)}</div>}
      {snapshot.status === 'cancel_requested' && <p className={styles.muted}>已记录取消请求，等待任务收敛。</p>}
    </>}
  </section>;
}

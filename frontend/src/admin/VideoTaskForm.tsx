import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { useNavigate } from 'react-router';
import { ApiError, type AdminClient, type VideoTaskInput } from '../shared/api';
import { ErrorNotice } from '../shared/ErrorNotice';
import styles from './App.module.css';

export const videoDraftKeyStorage = 'frameread:video-task:draft-key';
export const videoDraftStorage = 'frameread:video-task:draft';

type VideoDraft = {
  key: string;
  url: string;
  mode: VideoTaskInput['mode'];
  depth: VideoTaskInput['depth'];
  focus: string;
  uncertain: boolean;
};

function newUuidV4(): string {
  if (typeof crypto === 'undefined' || typeof crypto.randomUUID !== 'function') {
    throw new Error('Secure random UUID generation is unavailable');
  }
  return crypto.randomUUID();
}

export function getOrCreateVideoDraftKey(): string {
  const existing = sessionStorage.getItem(videoDraftKeyStorage);
  if (existing) return existing;
  const created = newUuidV4();
  sessionStorage.setItem(videoDraftKeyStorage, created);
  return created;
}

type DraftReadResult = {
  draft: VideoDraft;
  blockedError: string | null;
};

const corruptDraftMessage = '保存的提交草稿已损坏，已阻止提交以保留原幂等键。请确认服务端未受理后清理当前会话草稿，再重新打开页面。';

function emptyDraft(key: string): VideoDraft {
  return { key, url: '', mode: 'complete', depth: 'standard', focus: '', uncertain: false };
}

function blockedDraft(key: string | null): DraftReadResult {
  return { draft: { ...emptyDraft(key ?? ''), uncertain: true }, blockedError: corruptDraftMessage };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function readDraft(): DraftReadResult {
  const pendingKey = sessionStorage.getItem(videoDraftKeyStorage);
  const raw = sessionStorage.getItem(videoDraftStorage);
  if (raw === null) {
    if (pendingKey !== null && !pendingKey) return blockedDraft(pendingKey);
    const key = pendingKey ?? getOrCreateVideoDraftKey();
    return { draft: emptyDraft(key), blockedError: null };
  }

  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return blockedDraft(pendingKey);
  }
  if (!isRecord(parsed) || typeof parsed.key !== 'string' || !parsed.key
    || (pendingKey !== null && pendingKey !== parsed.key)
    || (parsed.url !== undefined && typeof parsed.url !== 'string')
    || (parsed.mode !== undefined && parsed.mode !== 'complete' && parsed.mode !== 'topic')
    || (parsed.depth !== undefined && parsed.depth !== 'brief' && parsed.depth !== 'standard' && parsed.depth !== 'detailed')
    || (parsed.focus !== undefined && typeof parsed.focus !== 'string')
    || (parsed.uncertain !== undefined && typeof parsed.uncertain !== 'boolean')) {
    return blockedDraft(pendingKey ?? (isRecord(parsed) && typeof parsed.key === 'string' ? parsed.key : null));
  }

  return {
    draft: {
      key: parsed.key,
      url: parsed.url === undefined ? '' : parsed.url,
      mode: parsed.mode === 'topic' ? 'topic' : 'complete',
      depth: parsed.depth === 'brief' || parsed.depth === 'detailed' ? parsed.depth : 'standard',
      focus: parsed.focus === undefined ? '' : parsed.focus,
      uncertain: parsed.uncertain === true,
    },
    blockedError: null,
  };
}

function fieldErrors(error: unknown): Map<string, string> {
  if (!(error instanceof ApiError)) return new Map();
  return new Map(error.body.details?.filter((detail) => detail.field).map((detail) => [detail.field as string, detail.message]));
}

function validate(input: VideoTaskInput): Record<string, string> {
  const errors: Record<string, string> = {};
  if (!input.url.trim()) errors.url = '请输入视频链接';
  else {
    try {
      const parsed = new URL(input.url);
      if (parsed.protocol !== 'https:') errors.url = '视频链接必须使用 HTTPS';
    } catch {
      errors.url = '请输入有效的视频链接';
    }
  }
  if (input.mode === 'topic' && !input.focus?.trim()) errors.focus = 'topic 模式需要填写关注点';
  return errors;
}

export function VideoTaskForm({ api }: { api: AdminClient }) {
  const navigate = useNavigate();
  const [draftState, setDraftState] = useState(readDraft);
  const [clientErrors, setClientErrors] = useState<Record<string, string>>({});
  const { draft, blockedError } = draftState;
  const persistDraft = (next: VideoDraft) => {
    setDraftState({ draft: next, blockedError: null });
    sessionStorage.setItem(videoDraftStorage, JSON.stringify(next));
    sessionStorage.setItem(videoDraftKeyStorage, next.key);
  };
  const updateDraft = (changes: Partial<VideoDraft>) => {
    const next = { ...draft, ...changes };
    persistDraft(next);
  };
  const clearDraftForNextSubmission = () => {
    sessionStorage.removeItem(videoDraftKeyStorage);
    sessionStorage.removeItem(videoDraftStorage);
    setDraftState({ draft: { ...draft, key: newUuidV4(), uncertain: false }, blockedError: null });
  };
  const mutation = useMutation({
    mutationFn: (input: VideoTaskInput) => api.createVideoTask(input, draft.key),
    retry: false,
    onSuccess: (accepted) => {
      sessionStorage.removeItem(videoDraftKeyStorage);
      sessionStorage.removeItem(videoDraftStorage);
      void navigate(`/manage/tasks/${encodeURIComponent(accepted.task_id)}`);
    },
    onError: (error) => {
      if (error instanceof ApiError && error.status >= 400 && error.status < 500) {
        clearDraftForNextSubmission();
      } else {
        const next = { ...draft, uncertain: true };
        setDraftState({ draft: next, blockedError: null });
        sessionStorage.setItem(videoDraftStorage, JSON.stringify(next));
      }
    },
  });
  const serverErrors = fieldErrors(mutation.error);
  const errors = { ...Object.fromEntries(serverErrors), ...clientErrors };
  const input: VideoTaskInput = {
    url: draft.url.trim(), mode: draft.mode, depth: draft.depth, focus: draft.focus.trim() || null,
    provider_config_id: null, asr_config_id: null, intent: 'new',
  };

  return <section className={styles.taskPage} aria-labelledby="new-video-title">
    <div className={styles.pageHeading}>
      <div>
        <p className={styles.eyebrow}>视频解读</p>
        <h1 id="new-video-title">提交视频任务</h1>
        <p>任务会先进入队列。S0 只验证受理和任务状态，不会生成文章。</p>
      </div>
      <button className={styles.linkButton} type="button" onClick={() => void navigate('/manage/')}>返回管理首页</button>
    </div>
    <form className={styles.taskForm} onSubmit={(event) => {
      event.preventDefault();
      if (mutation.isPending || blockedError) return;
      const nextErrors = validate(input);
      setClientErrors(nextErrors);
      if (Object.keys(nextErrors).length) return;
      persistDraft({ ...draft, uncertain: false });
      mutation.mutate(input);
    }}>
      <div className={styles.field}>
        <label htmlFor="video-url">视频链接</label>
        <input id="video-url" name="url" type="url" required value={draft.url}
          disabled={draft.uncertain || Boolean(blockedError)}
          onChange={(event) => { updateDraft({ url: event.target.value }); setClientErrors((current) => ({ ...current, url: '' })); }}
          aria-invalid={Boolean(errors.url)} aria-describedby={errors.url ? 'video-url-error' : undefined}
          placeholder="https://www.youtube.com/watch?v=…" />
        {errors.url && <p id="video-url-error" className={styles.fieldError}>{errors.url}</p>}
      </div>
      <div className={styles.formGrid}>
        <div className={styles.field}>
          <label htmlFor="video-mode">解读模式</label>
          <select id="video-mode" name="mode" value={draft.mode} disabled={draft.uncertain || Boolean(blockedError)} onChange={(event) => updateDraft({ mode: event.target.value as VideoTaskInput['mode'] })}>
            <option value="complete">完整解读</option>
            <option value="topic">关注主题</option>
          </select>
        </div>
        <div className={styles.field}>
          <label htmlFor="video-depth">解读深度</label>
          <select id="video-depth" name="depth" value={draft.depth} disabled={draft.uncertain || Boolean(blockedError)} onChange={(event) => updateDraft({ depth: event.target.value as VideoTaskInput['depth'] })}>
            <option value="brief">简要</option>
            <option value="standard">标准</option>
            <option value="detailed">详细</option>
          </select>
        </div>
      </div>
      <div className={styles.field}>
        <label htmlFor="video-focus">关注点 <span className={styles.optional}>可选，topic 模式必填</span></label>
        <textarea id="video-focus" name="focus" rows={4} maxLength={2000} value={draft.focus}
          disabled={draft.uncertain || Boolean(blockedError)}
          onChange={(event) => { updateDraft({ focus: event.target.value }); setClientErrors((current) => ({ ...current, focus: '' })); }}
          aria-invalid={Boolean(errors.focus)} aria-describedby={errors.focus ? 'video-focus-error' : undefined}
          placeholder="例如：梳理作者提出的三个核心论点" />
        {errors.focus && <p id="video-focus-error" className={styles.fieldError}>{errors.focus}</p>}
      </div>
      <button className={styles.primary} type="submit" disabled={mutation.isPending || Boolean(blockedError)}>
        {mutation.isPending ? '正在提交…' : '提交视频任务'}
      </button>
      {draft.uncertain && <p className={styles.draftNotice} role="status">受理结果未确认。请使用原操作标识重试，表单内容已锁定以避免重复提交不同请求。</p>}
      {blockedError && <p className={styles.draftNotice} role="alert">{blockedError}</p>}
      <ErrorNotice error={mutation.error} handledFields={['url', 'mode', 'depth', 'focus']} />
    </form>
  </section>;
}

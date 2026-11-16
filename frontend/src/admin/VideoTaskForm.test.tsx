import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createMemoryRouter, RouterProvider } from 'react-router';
import { describe, expect, it, vi } from 'vitest';
import { createAdminClient } from '../shared/api';
import { videoDraftKeyStorage, videoDraftStorage, VideoTaskForm } from './VideoTaskForm';

function mount(fetcher: typeof fetch) {
  const api = createAdminClient({ fetcher });
  const router = createMemoryRouter([{ path: '*', element: <VideoTaskForm api={api} /> }], { initialEntries: ['/manage/videos/new'] });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  render(<QueryClientProvider client={client}><RouterProvider router={router} /></QueryClientProvider>);
  return router;
}

function errorResponse(
  status: number,
  details: Array<{ field: string; code: string; message: string }> = [],
  code = status === 503 ? 'QUEUE_FULL' : status === 404 ? 'NOT_FOUND' : 'INVALID_INPUT',
  action = status === 503 ? 'retry_later' : 'none',
) {
  return Response.json({ error: {
    code, message: '请求未完成', action,
    request_id: 'request-video', retry_after_seconds: status === 503 ? 2 : null, task_id: null, details,
  } }, { status });
}

describe('video task submission form', () => {
  it('blocks a corrupt persisted draft without discarding its pending idempotency key', async () => {
    sessionStorage.clear();
    const key = '44444444-4444-4444-8444-444444444444';
    const corruptDraft = '{"key":';
    sessionStorage.setItem(videoDraftKeyStorage, key);
    sessionStorage.setItem(videoDraftStorage, corruptDraft);
    const fetcher = vi.fn<typeof fetch>();

    mount(fetcher);

    expect(await screen.findByRole('alert')).toHaveTextContent('保存的提交草稿已损坏');
    expect(screen.getByRole('button', { name: '提交视频任务' })).toBeDisabled();
    expect(screen.getByLabelText('视频链接')).toBeDisabled();
    expect(sessionStorage.getItem(videoDraftKeyStorage)).toBe(key);
    expect(sessionStorage.getItem(videoDraftStorage)).toBe(corruptDraft);
    expect(fetcher).not.toHaveBeenCalled();
  });

  it('also blocks an empty persisted draft instead of silently creating a new key', async () => {
    sessionStorage.clear();
    const key = '55555555-5555-4555-8555-555555555555';
    sessionStorage.setItem(videoDraftKeyStorage, key);
    sessionStorage.setItem(videoDraftStorage, '');
    const fetcher = vi.fn<typeof fetch>();

    mount(fetcher);

    expect(await screen.findByRole('alert')).toBeVisible();
    expect(sessionStorage.getItem(videoDraftKeyStorage)).toBe(key);
    expect(sessionStorage.getItem(videoDraftStorage)).toBe('');
    expect(fetcher).not.toHaveBeenCalled();
  });

  it('blocks an empty pending key instead of replacing an unknown idempotency key', async () => {
    sessionStorage.clear();
    sessionStorage.setItem(videoDraftKeyStorage, '');
    const fetcher = vi.fn<typeof fetch>();

    mount(fetcher);

    expect(await screen.findByRole('alert')).toBeVisible();
    expect(sessionStorage.getItem(videoDraftKeyStorage)).toBe('');
    expect(fetcher).not.toHaveBeenCalled();
  });

  it('keeps the same draft key after a 503 retry', async () => {
    sessionStorage.clear();
    const key = '11111111-1111-4111-8111-111111111111';
    sessionStorage.setItem(videoDraftKeyStorage, key);
    const fetcher = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(errorResponse(503))
      .mockResolvedValueOnce(Response.json({ task_id: 'task-1', kind: 'video', status: 'queued', accepted_at: '2026-11-16T00:00:00Z', deadline_at: '2026-11-16T02:00:00Z', snapshot_url: '/api/v1/admin/tasks/task-1', replayed: false, operation_scope: 'video:new' }, { status: 202 }));
    const router = mount(fetcher);
    const user = userEvent.setup();
    await user.type(screen.getByLabelText('视频链接'), 'https://www.youtube.com/watch?v=abc123');
    await user.click(screen.getByRole('button', { name: '提交视频任务' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('请求未完成');
    expect(sessionStorage.getItem(videoDraftKeyStorage)).toBe(key);
    await user.click(screen.getByRole('button', { name: '提交视频任务' }));
    expect(router.state.location.pathname).toBe('/manage/tasks/task-1');
    expect(new Headers(fetcher.mock.calls[0]?.[1]?.headers).get('Idempotency-Key')).toBe(key);
    expect(new Headers(fetcher.mock.calls[1]?.[1]?.headers).get('Idempotency-Key')).toBe(key);
    expect(sessionStorage.getItem(videoDraftKeyStorage)).toBeNull();
  });

  it('shows topic focus validation before sending', async () => {
    const fetcher = vi.fn<typeof fetch>();
    mount(fetcher);
    const user = userEvent.setup();
    await user.type(screen.getByLabelText('视频链接'), 'https://www.youtube.com/watch?v=abc123');
    await user.selectOptions(screen.getByLabelText('解读模式'), 'topic');
    await user.click(screen.getByRole('button', { name: '提交视频任务' }));
    expect(screen.getByText('topic 模式需要填写关注点')).toBeVisible();
    expect(fetcher).not.toHaveBeenCalled();
  });

  it('clears the draft key after a definitive 422', async () => {
    sessionStorage.clear();
    const oldKey = '33333333-3333-4333-8333-333333333333';
    sessionStorage.setItem(videoDraftKeyStorage, oldKey);
    const fetcher = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(errorResponse(422, [{ field: 'url', code: 'invalid', message: '链接不支持' }]))
      .mockResolvedValueOnce(Response.json({
        task_id: 'task-3', kind: 'video', status: 'queued', accepted_at: '2026-11-16T00:00:00Z',
        deadline_at: '2026-11-16T02:00:00Z', snapshot_url: '/api/v1/admin/tasks/task-3', replayed: false, operation_scope: 'video:new',
      }, { status: 202 }));
    mount(fetcher);
    const user = userEvent.setup();
    await user.type(screen.getByLabelText('视频链接'), 'https://www.youtube.com/watch?v=abc123');
    await user.click(screen.getByRole('button', { name: '提交视频任务' }));
    expect(await screen.findByText('链接不支持')).toBeVisible();
    expect(sessionStorage.getItem(videoDraftKeyStorage)).toBeNull();
    await user.click(screen.getByRole('button', { name: '提交视频任务' }));
    const nextKey = new Headers(fetcher.mock.calls[1]?.[1]?.headers).get('Idempotency-Key');
    expect(nextKey).toBeTruthy();
    expect(nextKey).not.toBe(oldKey);
  });

  it('restores fields after refresh and keeps the original key while uncertain', async () => {
    const oldKey = '22222222-2222-4222-8222-222222222222';
    sessionStorage.setItem(videoDraftStorage, JSON.stringify({
      key: oldKey, url: 'https://www.youtube.com/watch?v=old', mode: 'complete', depth: 'standard', focus: '', uncertain: true,
    }));
    sessionStorage.setItem(videoDraftKeyStorage, oldKey);
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(Response.json({
      task_id: 'task-2', kind: 'video', status: 'queued', accepted_at: '2026-11-16T00:00:00Z',
      deadline_at: '2026-11-16T02:00:00Z', snapshot_url: '/api/v1/admin/tasks/task-2', replayed: false, operation_scope: 'video:new',
    }, { status: 202 }));
    mount(fetcher);
    const user = userEvent.setup();
    expect(screen.getByLabelText('视频链接')).toHaveValue('https://www.youtube.com/watch?v=old');
    expect(screen.getByLabelText('视频链接')).toBeDisabled();
    await user.click(screen.getByRole('button', { name: '用原操作标识重试' }));
    const submittedKey = new Headers(fetcher.mock.calls[0]?.[1]?.headers).get('Idempotency-Key');
    expect(submittedKey).toBe(oldKey);
  });

  it('persists uncertain before a response-loss failure and locks the original input', async () => {
    sessionStorage.clear();
    const key = '66666666-6666-4666-8666-666666666666';
    sessionStorage.setItem(videoDraftKeyStorage, key);
    const fetcher = vi.fn<typeof fetch>().mockRejectedValueOnce(new TypeError('connection closed'));
    mount(fetcher);
    const user = userEvent.setup();
    await user.type(screen.getByLabelText('视频链接'), 'https://www.youtube.com/watch?v=lost-response');
    await user.click(screen.getByRole('button', { name: '提交视频任务' }));
    expect(await screen.findByText(/受理结果未确认/)).toBeVisible();
    expect(screen.getByLabelText('视频链接')).toBeDisabled();
    expect(screen.getByRole('button', { name: '用原操作标识重试' })).toBeEnabled();
    expect(JSON.parse(sessionStorage.getItem(videoDraftStorage) as string)).toMatchObject({ key, uncertain: true });
    expect(sessionStorage.getItem(videoDraftKeyStorage)).toBe(key);
  });

  it('keeps known queue and dependency failures distinct without marking admission uncertain', async () => {
    for (const code of ['QUEUE_FULL', 'DEPENDENCY_UNAVAILABLE'] as const) {
      sessionStorage.clear();
      const key = code === 'QUEUE_FULL' ? '77777777-7777-4777-8777-777777777777' : '88888888-8888-4888-8888-888888888888';
      sessionStorage.setItem(videoDraftKeyStorage, key);
      const fetcher = vi.fn<typeof fetch>().mockResolvedValueOnce(errorResponse(
        503,
        [],
        code,
        'retry_later',
      ));
      mount(fetcher);
      const user = userEvent.setup();
      await user.type(screen.getByLabelText('视频链接'), 'https://www.youtube.com/watch?v=known-503');
      await user.click(screen.getByRole('button', { name: '提交视频任务' }));
      expect(await screen.findByRole('alert')).toHaveTextContent(code === 'QUEUE_FULL' ? '排队已满' : '依赖服务暂不可用');
      expect(screen.queryByText(/受理结果未确认/)).not.toBeInTheDocument();
      expect(screen.getByLabelText('视频链接')).toBeEnabled();
      expect(sessionStorage.getItem(videoDraftKeyStorage)).toBe(key);
      cleanup();
    }
  });

  it('queries an uncertain operation with the same key and keeps it after a 404', async () => {
    sessionStorage.clear();
    const key = '99999999-9999-4999-8999-999999999999';
    sessionStorage.setItem(videoDraftKeyStorage, key);
    const fetcher = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(errorResponse(503, [], 'ADMISSION_UNCONFIRMED', 'resolve_same_key'))
      .mockResolvedValueOnce(errorResponse(404))
      .mockResolvedValueOnce(Response.json({
        task_id: 'task-recovered', kind: 'video', status: 'queued', accepted_at: '2026-11-16T00:00:00Z',
        deadline_at: '2026-11-16T02:00:00Z', snapshot_url: '/api/v1/admin/tasks/task-recovered', replayed: true,
        operation_scope: 'video:new',
      }, { status: 202 }));
    const router = mount(fetcher);
    const user = userEvent.setup();
    await user.type(screen.getByLabelText('视频链接'), 'https://www.youtube.com/watch?v=uncertain');
    await user.click(screen.getByRole('button', { name: '提交视频任务' }));
    await screen.findByText(/受理结果未确认/);
    await user.click(screen.getByRole('button', { name: '查询原操作' }));
    expect(await screen.findByText('暂未找到原操作，请继续使用原操作标识重试。')).toBeVisible();
    expect(sessionStorage.getItem(videoDraftKeyStorage)).toBe(key);
    await user.click(screen.getByRole('button', { name: '用原操作标识重试' }));
    expect(router.state.location.pathname).toBe('/manage/tasks/task-recovered');
    expect(new Headers(fetcher.mock.calls[0]?.[1]?.headers).get('Idempotency-Key')).toBe(key);
    expect(new Headers(fetcher.mock.calls[2]?.[1]?.headers).get('Idempotency-Key')).toBe(key);
  });

  it('persists and locks the request while its first response is still pending', async () => {
    sessionStorage.clear();
    const key = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
    sessionStorage.setItem(videoDraftKeyStorage, key);
    let reply!: (response: Response) => void;
    const fetcher = vi.fn<typeof fetch>().mockImplementation(() => new Promise((resolve) => { reply = resolve; }));
    mount(fetcher);
    const user = userEvent.setup();
    const url = 'https://youtu.be/dQw4w9WgXcQ?pending=true';
    await user.type(screen.getByLabelText('视频链接'), url);
    await user.click(screen.getByRole('button', { name: '提交视频任务' }));
    expect(screen.getByLabelText('视频链接')).toBeDisabled();
    expect(screen.getByRole('button', { name: '正在提交…' })).toBeDisabled();
    expect(JSON.parse(sessionStorage.getItem(videoDraftStorage) as string)).toMatchObject({ key, url, uncertain: true });
    expect(fetcher).toHaveBeenCalledTimes(1);
    reply(errorResponse(503));
    await screen.findByRole('alert');
  });

  it('waits for an operation lookup before permitting a concurrent retry', async () => {
    sessionStorage.clear();
    const key = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';
    sessionStorage.setItem(videoDraftKeyStorage, key);
    sessionStorage.setItem(videoDraftStorage, JSON.stringify({
      key, url: 'https://youtu.be/dQw4w9WgXcQ', mode: 'complete', depth: 'standard', focus: '', uncertain: true,
    }));
    let reply!: (response: Response) => void;
    const fetcher = vi.fn<typeof fetch>().mockImplementation(() => new Promise((resolve) => { reply = resolve; }));
    const router = mount(fetcher);
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: '查询原操作' }));
    expect(screen.getByRole('button', { name: '正在查询…' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '用原操作标识重试' })).toBeDisabled();
    reply(Response.json({
      task_id: 'task-found', kind: 'video', status: 'queued', accepted_at: '2026-11-16T00:00:00Z',
      deadline_at: '2026-11-16T02:00:00Z', snapshot_url: '/api/v1/admin/tasks/task-found', replayed: true,
      operation_scope: 'video:new',
    }));
    await screen.findByRole('heading', { name: '提交视频任务' });
    await vi.waitFor(() => expect(router.state.location.pathname).toBe('/manage/tasks/task-found'));
    expect(sessionStorage.getItem(videoDraftKeyStorage)).toBeNull();
    expect(fetcher).toHaveBeenCalledTimes(1);
  });
});

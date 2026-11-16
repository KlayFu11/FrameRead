import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
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

function errorResponse(status: number, details: Array<{ field: string; code: string; message: string }> = []) {
  return Response.json({ error: {
    code: status === 503 ? 'QUEUE_FULL' : 'INVALID_INPUT', message: '请求未完成', action: 'fix_input',
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
    await user.click(screen.getByRole('button', { name: '提交视频任务' }));
    const submittedKey = new Headers(fetcher.mock.calls[0]?.[1]?.headers).get('Idempotency-Key');
    expect(submittedKey).toBe(oldKey);
  });
});

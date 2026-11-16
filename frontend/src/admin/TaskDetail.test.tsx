import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render, screen, waitFor } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router';
import { describe, expect, it, vi } from 'vitest';
import { createAdminClient, type TaskSnapshot } from '../shared/api';
import { TaskDetail } from './TaskDetail';

function snapshot(overrides: Partial<TaskSnapshot> = {}): TaskSnapshot {
  return {
    id: 'task-1', kind: 'video', intent: 'new', status: 'queued', stage: null,
    state_revision: 1, event_seq: 1, cursor: 'cursor', instance_epoch: '00000000-0000-4000-8000-000000000001',
    attempt_no: 0, progress: { stage: null, observed_at: '2026-11-16T00:00:00Z' },
    deadline_at: '2026-11-16T02:00:00Z', cancel_requested_at: null, result: null, error: null,
    draft_summary: null, allowed_actions: ['cancel'], unknown_call_count: 0, ...overrides,
  };
}

function mount(fetcher: typeof fetch) {
  const api = createAdminClient({ fetcher });
  const router = createMemoryRouter([{ path: '*', element: <TaskDetail api={api} taskId="task-1" /> }], { initialEntries: ['/manage/tasks/task-1'] });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  render(<QueryClientProvider client={client}><RouterProvider router={router} /></QueryClientProvider>);
}

describe('task detail polling', () => {
  it('keeps the request ID visible for a 404 response', async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(Response.json({ error: {
      code: 'NOT_FOUND', message: '资源不存在', action: 'none', request_id: 'request-task-not-found',
      retry_after_seconds: null, task_id: null, details: [],
    } }, { status: 404 }));
    mount(fetcher);
    expect(await screen.findByText('request-task-not-found')).toBeVisible();
    expect(screen.getByRole('button', { name: '复制 request ID' })).toBeVisible();
  });

  it('continues polling after an older terminal response is rejected', async () => {
    vi.useFakeTimers();
    try {
      const fetcher = vi.fn<typeof fetch>()
        .mockResolvedValueOnce(Response.json(snapshot({ status: 'running', state_revision: 5 })))
        .mockResolvedValueOnce(Response.json(snapshot({ status: 'failed', state_revision: 4 })))
        .mockResolvedValueOnce(Response.json(snapshot({ status: 'canceled', state_revision: 6, allowed_actions: [] })));
      mount(fetcher);
      await act(async () => { await vi.advanceTimersByTimeAsync(0); await Promise.resolve(); await Promise.resolve(); });
      expect(screen.getByText('运行中')).toBeVisible();
      await act(async () => { await vi.advanceTimersByTimeAsync(2000); });
      expect(screen.getByText('运行中')).toBeVisible();
      expect(fetcher).toHaveBeenCalledTimes(2);
      await act(async () => { await vi.advanceTimersByTimeAsync(2000); });
      expect(fetcher).toHaveBeenCalledTimes(3);
      expect(screen.getByText('已取消')).toBeVisible();
    } finally {
      vi.clearAllTimers();
      vi.useRealTimers();
    }
  });

  it('clears the stale banner after an identical successful snapshot', async () => {
    vi.useFakeTimers();
    try {
      const first = snapshot();
      const fetcher = vi.fn<typeof fetch>()
        .mockResolvedValueOnce(Response.json(first))
        .mockRejectedValueOnce(new TypeError('network down'))
        .mockResolvedValueOnce(Response.json(first));
      mount(fetcher);
      await act(async () => { await vi.advanceTimersByTimeAsync(0); await Promise.resolve(); await Promise.resolve(); });
      expect(screen.getByText('排队中')).toBeVisible();

      await act(async () => { await vi.advanceTimersByTimeAsync(2000); });
      await act(async () => { await vi.advanceTimersByTimeAsync(1); await Promise.resolve(); await Promise.resolve(); });
      expect(fetcher).toHaveBeenCalledTimes(2);
      expect(screen.getByText(/连接中断/)).toBeVisible();

      await act(async () => { await vi.advanceTimersByTimeAsync(4000); });
      expect(fetcher).toHaveBeenCalledTimes(3);
      expect(screen.queryByText(/连接中断/)).not.toBeInTheDocument();
    } finally {
      vi.clearAllTimers();
      vi.useRealTimers();
    }
  });

  it('backs off failed polls up to thirty seconds and resets after recovery', async () => {
    vi.useFakeTimers();
    try {
      const fetcher = vi.fn<typeof fetch>()
        .mockResolvedValueOnce(Response.json(snapshot()))
        .mockRejectedValueOnce(new TypeError('network down 1'))
        .mockRejectedValueOnce(new TypeError('network down 2'))
        .mockRejectedValueOnce(new TypeError('network down 3'))
        .mockRejectedValueOnce(new TypeError('network down 4'))
        .mockResolvedValueOnce(Response.json(snapshot({ state_revision: 2, status: 'running' })))
        .mockResolvedValue(Response.json(snapshot({ state_revision: 3, status: 'running' })));
      mount(fetcher);
      await act(async () => { await vi.advanceTimersByTimeAsync(0); await Promise.resolve(); await Promise.resolve(); });

      await act(async () => { await vi.advanceTimersByTimeAsync(2000); });
      await act(async () => { await vi.advanceTimersByTimeAsync(0); await Promise.resolve(); await Promise.resolve(); });
      expect(fetcher).toHaveBeenCalledTimes(2);
      await act(async () => { await vi.advanceTimersByTimeAsync(3999); });
      expect(fetcher).toHaveBeenCalledTimes(2);
      await act(async () => { await vi.advanceTimersByTimeAsync(1); });
      await act(async () => { await vi.advanceTimersByTimeAsync(0); await Promise.resolve(); await Promise.resolve(); });
      expect(fetcher).toHaveBeenCalledTimes(3);
      await act(async () => { await vi.advanceTimersByTimeAsync(7999); });
      expect(fetcher).toHaveBeenCalledTimes(3);
      await act(async () => { await vi.advanceTimersByTimeAsync(1); });
      await act(async () => { await vi.advanceTimersByTimeAsync(0); await Promise.resolve(); await Promise.resolve(); });
      expect(fetcher).toHaveBeenCalledTimes(4);
      await act(async () => { await vi.advanceTimersByTimeAsync(15999); });
      expect(fetcher).toHaveBeenCalledTimes(4);
      await act(async () => { await vi.advanceTimersByTimeAsync(1); });
      await act(async () => { await vi.advanceTimersByTimeAsync(0); await Promise.resolve(); await Promise.resolve(); });
      expect(fetcher).toHaveBeenCalledTimes(5);
      await act(async () => { await vi.advanceTimersByTimeAsync(29999); });
      expect(fetcher).toHaveBeenCalledTimes(5);
      await act(async () => { await vi.advanceTimersByTimeAsync(1); });
      await act(async () => { await vi.advanceTimersByTimeAsync(0); await Promise.resolve(); await Promise.resolve(); });
      expect(fetcher).toHaveBeenCalledTimes(6);
      await act(async () => { await vi.advanceTimersByTimeAsync(1999); });
      expect(fetcher).toHaveBeenCalledTimes(6);
      await act(async () => { await vi.advanceTimersByTimeAsync(1); });
      await act(async () => { await Promise.resolve(); await Promise.resolve(); });
      expect(fetcher).toHaveBeenCalledTimes(7);
    } finally {
      vi.clearAllTimers();
      vi.useRealTimers();
    }
  });

  it('pauses polling while the page is hidden', async () => {
    vi.useFakeTimers();
    const originalVisibility = document.visibilityState;
    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'hidden' });
    try {
      const fetcher = vi.fn<typeof fetch>().mockResolvedValue(Response.json(snapshot()));
      mount(fetcher);
      await act(async () => { await vi.advanceTimersByTimeAsync(0); await Promise.resolve(); await Promise.resolve(); });
      await act(async () => { await vi.advanceTimersByTimeAsync(10000); });
      expect(fetcher).toHaveBeenCalledTimes(1);
    } finally {
      Object.defineProperty(document, 'visibilityState', { configurable: true, value: originalVisibility });
      vi.clearAllTimers();
      vi.useRealTimers();
    }
  });

  it('shows the last successful sync time after ten seconds without a fresh response', async () => {
    vi.useFakeTimers();
    try {
      const fetcher = vi.fn<typeof fetch>()
        .mockResolvedValueOnce(Response.json(snapshot()))
        .mockRejectedValue(new TypeError('network down'));
      mount(fetcher);
      await act(async () => { await vi.advanceTimersByTimeAsync(0); await Promise.resolve(); await Promise.resolve(); });
      expect(screen.queryByText(/上次成功同步/)).not.toBeInTheDocument();
      await act(async () => { await vi.advanceTimersByTimeAsync(10000); });
      expect(screen.getByText(/上次成功同步/)).toBeVisible();
    } finally {
      vi.clearAllTimers();
      vi.useRealTimers();
    }
  });

  it('polls every two seconds and stops after a terminal snapshot', async () => {
    const fetcher = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(Response.json(snapshot()))
      .mockResolvedValueOnce(Response.json(snapshot({ status: 'succeeded', state_revision: 2, allowed_actions: [] })))
      .mockResolvedValue(Response.json(snapshot({ status: 'failed', state_revision: 3, allowed_actions: [] })));
    mount(fetcher);
    await screen.findByText('排队中');
    expect(fetcher).toHaveBeenCalledTimes(1);
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 2100)); });
    await screen.findByText('已完成');
    expect(fetcher).toHaveBeenCalledTimes(2);
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 2200)); });
    expect(fetcher).toHaveBeenCalledTimes(2);
  }, 10000);

  it('keeps the last snapshot and marks the page stale after a failed poll', async () => {
    const fetcher = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(Response.json(snapshot()))
      .mockRejectedValue(new TypeError('network down'));
    mount(fetcher);
    await screen.findByText('排队中');
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 2100)); });
    await waitFor(() => expect(screen.getByText(/连接中断/)).toBeVisible());
    expect(screen.getByText('排队中')).toBeVisible();
  }, 10000);
});

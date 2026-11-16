import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { BrowserRouter, createMemoryRouter, RouterProvider } from 'react-router';
import { describe, expect, it, vi } from 'vitest';
import { AdminApp } from './App';

function mount(path = '/manage/', returnTo?: string) {
  const router = createMemoryRouter([{ path: '*', element: <AdminApp /> }], {
    initialEntries: returnTo ? [{ pathname: path, state: { returnTo } }] : [path],
  });
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  render(<QueryClientProvider client={queryClient}><RouterProvider router={router} /></QueryClientProvider>);
  return router;
}

function taskSnapshot(taskId: string) {
  return {
    id: taskId, kind: 'video', intent: 'new', status: 'queued', stage: null,
    state_revision: 1, event_seq: 1, cursor: 'cursor', instance_epoch: '00000000-0000-4000-8000-000000000001',
    attempt_no: 0, progress: { stage: null, observed_at: '2026-11-16T00:00:00Z' },
    deadline_at: '2026-11-16T02:00:00Z', cancel_requested_at: null, result: null, error: null,
    draft_summary: null, allowed_actions: ['cancel'], unknown_call_count: 0,
  };
}

function adminRequired() {
  return Response.json({ error: {
    code: 'ADMIN_REQUIRED', message: '需要登录', action: 'login', request_id: 'request-probe',
  } }, { status: 401 });
}

describe('管理员登录与外壳', () => {
  it('resets task detail state when navigation changes to another task', async () => {
    let resolveTaskB: ((response: Response) => void) | undefined;
    const taskB = new Promise<Response>((resolve) => { resolveTaskB = resolve; });
    const fetcher = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(Response.json({ csrf_token: 'csrf-existing', expires_at: '2026-11-16T23:00:00Z' }))
      .mockResolvedValueOnce(Response.json(taskSnapshot('task-a')))
      .mockImplementationOnce(() => taskB);
    vi.stubGlobal('fetch', fetcher);
    const router = mount('/manage/tasks/task-a');

    expect(await screen.findByText('排队中')).toBeVisible();
    await act(async () => { await router.navigate('/manage/tasks/task-b'); });

    expect(await screen.findByRole('status')).toHaveTextContent('正在读取任务快照');
    expect(screen.queryByText('排队中')).not.toBeInTheDocument();
    resolveTaskB?.(Response.json(taskSnapshot('task-b')));
  });

  it('直接打开登录页也探测会话，已有有效会话时进入管理外壳', async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(Response.json({
      csrf_token: 'csrf-existing', expires_at: '2026-11-16T23:00:00Z',
    }));
    vi.stubGlobal('fetch', fetcher);
    const router = mount('/manage/login');

    expect(await screen.findByRole('heading', { name: '管理入口已就绪' })).toBeVisible();
    expect(router.state.location.pathname).toBe('/manage/');
    expect(fetcher).toHaveBeenCalledWith('/api/v1/admin/session', expect.objectContaining({ method: 'GET' }));
    expect(screen.queryByLabelText('管理员密码')).not.toBeInTheDocument();
  });

  it.each([
    ['/manage/?source=login#resume', '/manage/?source=login#resume'],
    ['https://example.org/', '/manage/'],
  ])('登录页初次探测401无循环且安全恢复 returnTo %s', async (returnTo, expected) => {
    const fetcher = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(adminRequired())
      .mockResolvedValueOnce(Response.json({ csrf_token: 'csrf-return', expires_at: '2026-11-16T23:00:00Z' }, { status: 201 }));
    vi.stubGlobal('fetch', fetcher);
    const router = mount('/manage/login', returnTo);
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText('管理员密码'), 'example-password');
    await user.click(screen.getByRole('button', { name: '登录' }));
    await screen.findByRole('heading', { name: '管理入口已就绪' });

    expect(router.state.location.pathname + router.state.location.search + router.state.location.hash).toBe(expected);
    expect(fetcher.mock.calls.map(([, options]) => options?.method)).toEqual(['GET', 'POST']);
  });

  it('未登录保留原路径，密码登录后回到原位置并能退出', async () => {
    const fetcher = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(Response.json({ error: {
        code: 'ADMIN_REQUIRED', message: '需要登录', action: 'login', request_id: 'request-login',
      } }, { status: 401 }))
      .mockResolvedValueOnce(Response.json({ csrf_token: 'csrf-login', expires_at: '2026-11-16T23:00:00Z' }, { status: 201 }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    vi.stubGlobal('fetch', fetcher);
    const router = mount('/manage/?view=home#start');
    const user = userEvent.setup();

    const password = await screen.findByLabelText('管理员密码');
    expect(document.querySelectorAll('input')).toHaveLength(1);
    expect(password).toHaveAttribute('type', 'password');
    await user.type(password, 'example-password');
    await user.click(screen.getByRole('button', { name: '登录' }));

    await screen.findByRole('heading', { name: '管理入口已就绪' });
    expect(router.state.location.pathname + router.state.location.search + router.state.location.hash).toBe('/manage/?view=home#start');
    expect(JSON.parse(fetcher.mock.calls[1]?.[1]?.body as string)).toEqual({ password: 'example-password' });
    await user.click(screen.getByRole('button', { name: '退出登录' }));
    await screen.findByRole('button', { name: '登录' });
    expect(router.state.location.pathname).toBe('/manage/login');
    expect(localStorage.length).toBe(0);
  });

  it('登录限流展示服务端 message、等待秒数、固定动作提示和可复制 request ID', async () => {
    vi.stubGlobal('fetch', vi.fn<typeof fetch>().mockResolvedValueOnce(adminRequired()).mockResolvedValue(Response.json({ error: {
      code: 'RATE_LIMITED', message: '登录尝试过多', action: 'retry_later',
      request_id: 'd035b058-0e23-49e1-9c02-faa3cc5f663f', retry_after_seconds: 42,
    } }, { status: 429 })));
    mount('/manage/login');
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText('管理员密码'), 'example-password');
    await user.click(screen.getByRole('button', { name: '登录' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('登录尝试过多');
    expect(screen.getByRole('alert')).toHaveTextContent('请等待 42 秒后重试');
    expect(screen.getByRole('alert')).toHaveTextContent('请稍后重试');
    expect(screen.getByText('d035b058-0e23-49e1-9c02-faa3cc5f663f')).toBeVisible();
    expect(screen.getByRole('button', { name: '复制 request ID' })).toBeEnabled();
    const copy = vi.spyOn(navigator.clipboard, 'writeText').mockResolvedValue();
    await user.click(screen.getByRole('button', { name: '复制 request ID' }));
    expect(copy).toHaveBeenCalledWith('d035b058-0e23-49e1-9c02-faa3cc5f663f');
    expect(await screen.findByRole('status')).toHaveTextContent('已复制');
  });

  it.each([
    [401, 'ADMIN_REQUIRED', 'login', '密码错误，请重试', '请重新登录'],
    [403, 'ORIGIN_REJECTED', 'none', '来源被拒绝', '来源校验失败，请从管理入口地址访问。'],
  ])('登录错误 %s 留在登录页展示信息且不自动重试', async (status, code, action, message, expected) => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValueOnce(adminRequired()).mockResolvedValue(Response.json({ error: {
      code, action, message, request_id: 'request-rejected',
    } }, { status }));
    vi.stubGlobal('fetch', fetcher);
    const router = mount('/manage/login');
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText('管理员密码'), 'example-password');
    await user.click(screen.getByRole('button', { name: '登录' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(expected);
    expect(screen.getByRole('alert')).toHaveTextContent(message);
    expect(router.state.location.pathname).toBe('/manage/login');
    expect(fetcher.mock.calls.map(([, options]) => options?.method)).toEqual(['GET', 'POST']);
  });

  it('退出遇到 CSRF403 时提示刷新，仍保留外壳且不重放退出', async () => {
    const fetcher = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(Response.json({ csrf_token: 'csrf-old', expires_at: '2026-11-16T23:00:00Z' }))
      .mockResolvedValueOnce(Response.json({ error: {
        code: 'CSRF_REJECTED', message: '安全校验失败', action: 'refresh', request_id: 'request-csrf',
      } }, { status: 403 }))
      .mockResolvedValueOnce(Response.json({ csrf_token: 'csrf-new', expires_at: '2026-11-16T23:00:00Z' }));
    vi.stubGlobal('fetch', fetcher);
    mount();
    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: '退出登录' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('会话已重新获取，请刷新页面后重试。');
    expect(screen.getByRole('heading', { name: '管理入口已就绪' })).toBeVisible();
    expect(fetcher.mock.calls.map(([, options]) => options?.method)).toEqual(['GET', 'DELETE', 'GET']);
  });

  it('BrowserRouter 登录导航后仍能为退出附加登录取得的 CSRF', async () => {
    window.history.replaceState(null, '', '/manage/login');
    const fetcher = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(adminRequired())
      .mockResolvedValueOnce(Response.json({ csrf_token: 'csrf-navigation', expires_at: '2026-11-16T23:00:00Z' }, { status: 201 }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    vi.stubGlobal('fetch', fetcher);
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
    render(<QueryClientProvider client={queryClient}><BrowserRouter><AdminApp /></BrowserRouter></QueryClientProvider>);
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText('管理员密码'), 'example-password');
    await user.click(screen.getByRole('button', { name: '登录' }));
    await user.click(await screen.findByRole('button', { name: '退出登录' }));
    await screen.findByRole('button', { name: '登录' });

    expect(new Headers(fetcher.mock.calls[2]?.[1]?.headers).get('X-CSRF-Token')).toBe('csrf-navigation');
  });

  it('422 将密码错误关联输入框，未映射字段仍在表单顶部展示', async () => {
    vi.stubGlobal('fetch', vi.fn<typeof fetch>().mockResolvedValueOnce(adminRequired()).mockResolvedValue(Response.json({ error: {
      code: 'INVALID_INPUT', message: '请检查输入', action: 'fix_input', request_id: 'request-fields',
      details: [
        { field: 'password', code: 'invalid', message: '密码不符合要求' },
        { field: 'unknown', code: 'extra_forbidden', message: '存在未知字段' },
      ],
    } }, { status: 422 })));
    mount('/manage/login');
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText('管理员密码'), 'example-password');
    await user.click(screen.getByRole('button', { name: '登录' }));

    await screen.findByRole('alert');
    expect(screen.getByLabelText('管理员密码')).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByLabelText('管理员密码')).toHaveAccessibleDescription('密码不符合要求');
    expect(screen.getByRole('alert')).toHaveTextContent('存在未知字段');
    expect(screen.getByRole('alert')).not.toHaveTextContent('密码不符合要求');
  });
});

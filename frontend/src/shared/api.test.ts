import { describe, expect, it, vi } from 'vitest';
import { createAdminClient } from './api';

describe('管理请求层', () => {
  it('从会话恢复 CSRF 并随退出请求发送，凭据由浏览器 cookie 携带', async () => {
    const fetcher = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(Response.json({ csrf_token: 'csrf-one', expires_at: '2026-11-16T23:00:00Z' }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    const api = createAdminClient({ fetcher });

    await api.session();
    await api.logout();

    expect(fetcher).toHaveBeenLastCalledWith('/api/v1/admin/session', expect.objectContaining({
      method: 'DELETE', credentials: 'same-origin',
    }));
    const options = fetcher.mock.calls[1]?.[1];
    expect(new Headers(options?.headers).get('X-CSRF-Token')).toBe('csrf-one');
  });

  it('CSRF 拒绝后更新会话但不重放原写请求，下一次主动写使用新 token', async () => {
    const fetcher = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(Response.json({ csrf_token: 'csrf-old', expires_at: '2026-11-16T23:00:00Z' }))
      .mockResolvedValueOnce(Response.json({ error: {
        code: 'CSRF_REJECTED', message: 'CSRF rejected', action: 'refresh', request_id: 'request-csrf',
      } }, { status: 403 }))
      .mockResolvedValueOnce(Response.json({ csrf_token: 'csrf-new', expires_at: '2026-11-16T23:00:00Z' }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    const api = createAdminClient({ fetcher });
    await api.session();

    await expect(api.logout()).rejects.toMatchObject({ status: 403, body: { action: 'refresh' } });
    expect(fetcher.mock.calls.map(([, options]) => options?.method)).toEqual(['GET', 'DELETE', 'GET']);

    await api.logout();
    expect(new Headers(fetcher.mock.calls[3]?.[1]?.headers).get('X-CSRF-Token')).toBe('csrf-new');
  });

  it('受保护请求 401 通知路由恢复登录，不重试请求', async () => {
    const onUnauthorized = vi.fn();
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(Response.json({ error: {
      code: 'ADMIN_REQUIRED', message: '需要登录', action: 'login', request_id: 'request-auth',
    } }, { status: 401 }));
    const api = createAdminClient({ fetcher, onUnauthorized });

    await expect(api.session()).rejects.toMatchObject({ status: 401 });
    expect(onUnauthorized).toHaveBeenCalledOnce();
    expect(fetcher).toHaveBeenCalledOnce();
  });
});

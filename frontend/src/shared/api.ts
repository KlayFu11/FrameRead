import type { components } from '../gen/admin-api';

export type Session = components['schemas']['SessionResponse'];
export type LoginInput = components['schemas']['PasswordLogin'];
export type ErrorBody = components['schemas']['ErrorEnvelope']['error'];

export type VideoTaskInput = components['schemas']['VideoTaskCreate'];
export type TaskAccepted = components['schemas']['TaskAccepted'];
export type TaskSnapshot = components['schemas']['TaskSnapshot'];

export class ApiError extends Error {
  constructor(public readonly status: number, public readonly body: ErrorBody) {
    super(body.message);
    this.name = 'ApiError';
  }
}

type ClientOptions = {
  fetcher?: typeof fetch;
  onUnauthorized?: () => void;
};

export function createAdminClient({ fetcher = fetch, onUnauthorized }: ClientOptions = {}) {
  let csrfToken: string | null = null;

  async function request<T>(path: string, options: RequestInit = {}, authenticated = true): Promise<T> {
    const method = (options.method ?? 'GET').toUpperCase();
    const headers = new Headers(options.headers);
    if (!['GET', 'HEAD', 'OPTIONS'].includes(method) && csrfToken) {
      headers.set('X-CSRF-Token', csrfToken);
    }
    const response = await fetcher(`/api/v1/admin${path}`, {
      ...options, method, headers, credentials: 'same-origin',
    });
    if (!response.ok) {
      const envelope = await response.json() as { error: ErrorBody };
      if (response.status === 401 && authenticated) {
        csrfToken = null;
        onUnauthorized?.();
      }
      if (response.status === 403 && envelope.error.code === 'CSRF_REJECTED' && method !== 'GET') {
        await session();
      }
      throw new ApiError(response.status, envelope.error);
    }
    if (response.status === 204) return undefined as T;
    return response.json() as Promise<T>;
  }

  async function session(): Promise<Session> {
    const result = await request<Session>('/session');
    csrfToken = result.csrf_token;
    return result;
  }

  async function logout(): Promise<void> {
    await request<void>('/session', { method: 'DELETE' });
    csrfToken = null;
  }

  async function login(input: LoginInput): Promise<Session> {
    const result = await request<Session>('/session', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(input),
    }, false);
    csrfToken = result.csrf_token;
    return result;
  }

  async function createVideoTask(input: VideoTaskInput, idempotencyKey: string): Promise<TaskAccepted> {
    return request<TaskAccepted>('/video-tasks', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Idempotency-Key': idempotencyKey },
      body: JSON.stringify(input),
    });
  }

  async function taskSnapshot(taskId: string): Promise<TaskSnapshot> {
    return request<TaskSnapshot>(`/tasks/${encodeURIComponent(taskId)}`);
  }

  return { request, session, login, logout, createVideoTask, taskSnapshot };
}

export type AdminClient = ReturnType<typeof createAdminClient>;

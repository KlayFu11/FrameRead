import { useEffect, useMemo, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useLocation, useNavigate } from 'react-router';
import { ApiError, createAdminClient } from '../shared/api';
import { ErrorNotice } from '../shared/ErrorNotice';
import { TaskDetail } from './TaskDetail';
import { VideoTaskForm } from './VideoTaskForm';
import styles from './App.module.css';

const sessionKey = ['admin', 'session'];

function returnPath(value: unknown): string {
  return typeof value === 'string' && value.startsWith('/manage/') && !value.includes('\\')
    && value.split(/[?#]/)[0] !== '/manage/login' ? value : '/manage/';
}

export function AdminApp() {
  const location = useLocation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const currentPath = useRef('');
  const navigateRef = useRef(navigate);
  navigateRef.current = navigate;
  currentPath.current = location.pathname + location.search + location.hash;
  const isLogin = location.pathname === '/manage/login';
  const [loginRequired, setLoginRequired] = useState(false);
  const [password, setPassword] = useState('');
  const api = useMemo(() => createAdminClient({
    onUnauthorized: () => {
      setLoginRequired(true);
      queryClient.removeQueries({ queryKey: sessionKey });
      if (currentPath.current.split(/[?#]/)[0] === '/manage/login') return;
      void navigateRef.current('/manage/login', { replace: true, state: { returnTo: currentPath.current } });
    },
  }), [queryClient]);
  const session = useQuery({
    queryKey: sessionKey,
    queryFn: () => api.session(),
    enabled: !loginRequired,
    retry: false,
    staleTime: Infinity,
    refetchOnWindowFocus: false,
  });
  const login = useMutation({
    mutationFn: (value: string) => api.login({ password: value }),
    retry: false,
    onSuccess: (value) => {
      queryClient.setQueryData(sessionKey, value);
      setLoginRequired(false);
      const state = location.state as { returnTo?: unknown } | null;
      void navigate(returnPath(state?.returnTo), { replace: true });
    },
  });
  const logout = useMutation({
    mutationFn: () => api.logout(),
    retry: false,
    onSuccess: () => {
      setLoginRequired(true);
      queryClient.removeQueries({ queryKey: sessionKey });
      void navigate('/manage/login', { replace: true });
    },
  });
  useEffect(() => {
    if (!isLogin || loginRequired || !session.isSuccess) return;
    const state = location.state as { returnTo?: unknown } | null;
    void navigate(returnPath(state?.returnTo), { replace: true });
  }, [isLogin, loginRequired, session.isSuccess, location.state, navigate]);
  const passwordErrors = login.error instanceof ApiError && login.error.status === 422
    ? login.error.body.details?.filter((detail) => detail.field === 'password') ?? [] : [];
  const taskMatch = location.pathname.match(/^\/manage\/tasks\/([^/]+)$/);
  const authenticatedContent = location.pathname === '/manage/videos/new'
    ? <VideoTaskForm api={api} />
    : taskMatch ? <TaskDetail key={taskMatch[1]} api={api} taskId={decodeURIComponent(taskMatch[1])} />
      : <section className={styles.shell} aria-labelledby="shell-title">
        <div className={styles.sessionStatus}><span aria-hidden="true" /> 已登录</div>
        <h1 id="shell-title">管理入口已就绪</h1>
        <p>当前管理会话有效。</p>
        <p className={styles.expiry}>会话到期时间：{new Date(session.data?.expires_at ?? '').toLocaleString()}</p>
        <div className={styles.actionRow}>
          <button className={styles.primary} type="button" onClick={() => void navigate('/manage/videos/new')}>提交视频任务</button>
          <button className={styles.secondary} disabled={logout.isPending} onClick={() => logout.mutate()}>
            {logout.isPending ? '正在退出…' : '退出登录'}
          </button>
        </div>
        <ErrorNotice error={logout.error} />
      </section>;

  return <div className={styles.page}>
    <header className={styles.header}>
      <a className={styles.brand} href="/manage/">FrameRead<span className={styles.brandMark} aria-hidden="true" /></a>
      <span className={styles.headerLabel}>个人视频理解工作台</span>
    </header>
    <main className={styles.main}>
      {isLogin && loginRequired ? <section className={styles.login} aria-labelledby="login-title">
        <div className={styles.intro}>
          <h1 id="login-title">登录管理入口</h1>
          <p>输入管理员密码，进入你的 FrameRead。</p>
        </div>
        <form className={styles.form} onSubmit={(event) => {
          event.preventDefault();
          if (!password || login.isPending) return;
          login.mutate(password);
          setPassword('');
        }}>
          <label htmlFor="admin-password">管理员密码</label>
          <input id="admin-password" name="password" type="password" autoComplete="current-password"
            autoFocus required value={password} onChange={(event) => setPassword(event.target.value)}
            disabled={login.isPending} aria-invalid={passwordErrors.length > 0}
            aria-describedby={passwordErrors.length ? 'password-errors' : undefined} />
          {passwordErrors.length > 0 && <div id="password-errors">{passwordErrors.map((detail, index) => <p key={index}>{detail.message}</p>)}</div>}
          <button className={styles.primary} type="submit" disabled={login.isPending}>
            {login.isPending ? '正在登录…' : '登录'}
          </button>
        </form>
        <ErrorNotice error={login.error} handledFields={['password']} />
      </section> : session.isPending ? <p role="status">正在确认管理会话…</p>
        : session.isSuccess ? authenticatedContent : <section className={styles.shell}>
          <h1>暂时无法确认管理会话</h1>
          <ErrorNotice error={session.error} />
          <button className={styles.secondary} onClick={() => void session.refetch()}>重新连接</button>
        </section>}
    </main>
    <footer className={styles.footer}>FrameRead</footer>
  </div>;
}

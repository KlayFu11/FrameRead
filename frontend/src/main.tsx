import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AdminApp } from './admin/App';
import './style.css';

const root = document.getElementById('root');
if (!root) throw new Error('缺少应用 root 元素');
const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });

createRoot(root).render(<StrictMode><QueryClientProvider client={queryClient}>
  <BrowserRouter><AdminApp /></BrowserRouter>
</QueryClientProvider></StrictMode>);

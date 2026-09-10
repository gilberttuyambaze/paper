import { useEffect, useState, type ReactNode } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import { getAPIBaseURL } from '@/lib/config';

export default function MaintenanceGate({ children }: { children: ReactNode }) {
  const location = useLocation();
  const { user, hasPermission } = useAuth();
  const [status, setStatus] = useState<{ maintenance_mode: boolean; maintenance_message: string } | null>(null);

  useEffect(() => {
    let cancelled = false;
    const check = async () => {
      const controller = new AbortController();
      const timeout = window.setTimeout(() => controller.abort(), 5000);
      try {
        const response = await fetch(`${getAPIBaseURL()}/health/site-access`, { signal: controller.signal });
        if (!response.ok) throw new Error(`Site access check failed: ${response.status}`);
        const next = await response.json();
        if (!cancelled) setStatus(next);
      } catch {
        // Availability telemetry must never permanently lock users out when the
        // backend is starting, unavailable, or incorrectly configured.
        if (!cancelled) setStatus({ maintenance_mode: false, maintenance_message: '' });
      } finally {
        window.clearTimeout(timeout);
      }
    };
    void check();
    const timer = window.setInterval(() => void check(), 30000);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, []);

  const bypass = hasPermission('site.maintenance.bypass');
  const authPath = !user && (location.pathname.startsWith('/login') || location.pathname.startsWith('/forgot-password') || location.pathname.startsWith('/reset-password') || location.pathname.startsWith('/auth/'));
  if (status === null && !authPath && location.pathname !== '/locked' && location.pathname !== '/maintenance') {
    return <main className="flex min-h-screen items-center justify-center bg-background px-6 text-center"><p className="theme-muted">Checking site availability...</p></main>;
  }
  if (status?.maintenance_mode && !bypass && location.pathname === '/register') {
    return <Navigate to="/locked" replace />;
  }
  if (status?.maintenance_mode && !bypass && location.pathname !== '/locked' && location.pathname !== '/maintenance' && !authPath) {
    return <Navigate to="/locked" replace state={{ from: `${location.pathname}${location.search}${location.hash}` }} />;
  }
  return <>{children}</>;
}

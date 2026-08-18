import { FormEvent, useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import SeoMeta from '@/components/SeoMeta';
import { authApi } from '../lib/auth';

export default function ForgotPasswordPage() {
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [debugResetUrl, setDebugResetUrl] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const current = await authApi.getCurrentUser();
        if (!cancelled && current) {
          navigate('/past-papers?sort=-download_count', { replace: true });
        }
      } catch (_) {
        // ignore
      }
    })();
    return () => { cancelled = true; };
  }, [navigate]);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setLoading(true);
    setError(null);
    setMessage(null);
    setDebugResetUrl(null);

    try {
      const response = await authApi.requestPasswordReset(email);
      setMessage(response.message);
      setDebugResetUrl(response.debug_reset_url || null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to start password reset right now.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="theme-auth-page min-h-screen overflow-hidden px-4 py-8 md:px-8 md:py-10">
      <SeoMeta
        title="Forgot password"
        description="Request a password reset for UR Academic Resource Hub."
        canonicalPath="/forgot-password"
        robots="noindex,nofollow"
      />
      <div className="mx-auto flex min-h-[calc(100vh-4rem)] max-w-7xl items-center justify-center gap-6">
        <div className="flex items-center justify-center w-full">
          <div className="theme-auth-card w-full max-w-xl rounded-[2rem] p-8 md:p-10">
            <div className="mb-8">
              <p className="theme-link-accent mb-3 text-xs font-semibold uppercase tracking-[0.28em]">Password help</p>
              <h1 className="theme-title text-3xl font-bold md:text-4xl">Reset your password</h1>
              <p className="theme-muted mt-3 text-sm leading-6">
                Enter the email address linked to your account and we will prepare a secure password reset link.
              </p>
            </div>

            <form onSubmit={handleSubmit} className="space-y-5">
              <div>
                <Label htmlFor="email" className="theme-form-label">Email</Label>
                <Input
                  id="email"
                  type="email"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  placeholder="you@example.com"
                  required
                  className="theme-form-input mt-2 h-12 rounded-xl"
                />
              </div>

              {error && <p className="theme-error-note rounded-xl px-4 py-3 text-sm">{error}</p>}
              {message && <p className="theme-warning-note rounded-xl px-4 py-3 text-sm">{message}</p>}
              {debugResetUrl && (
                <div className="theme-soft-panel rounded-2xl px-4 py-4 text-sm">
                  <p className="theme-title font-semibold">Reset link</p>
                  <a href={debugResetUrl} className="theme-link-accent mt-2 block break-all underline underline-offset-4">
                    {debugResetUrl}
                  </a>
                </div>
              )}

              <Button
                type="submit"
                className="theme-accent-bg h-12 w-full rounded-xl"
                disabled={loading}
              >
                {loading ? 'Preparing reset link...' : 'Send reset link'}
              </Button>
            </form>

            <div className="theme-auth-subtle mt-6 rounded-2xl px-4 py-4 text-sm">
              <p>
                Remembered your password?{' '}
                <button
                  type="button"
                  onClick={() => navigate('/login')}
                  className="theme-link-accent font-semibold underline underline-offset-4"
                >
                  Back to sign in
                </button>
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

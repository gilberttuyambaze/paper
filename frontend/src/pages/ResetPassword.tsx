import { FormEvent, useMemo, useState } from 'react';
import { Eye, EyeOff } from 'lucide-react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import SeoMeta from '@/components/SeoMeta';
import AuthShowcase from '../components/AuthShowcase';
import { authApi } from '../lib/auth';

export default function ResetPasswordPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const token = useMemo(() => searchParams.get('token') || '', [searchParams]);
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setLoading(true);
    setError(null);
    setMessage(null);

    if (!token) {
      setError('This password reset link is missing its token.');
      setLoading(false);
      return;
    }

    if (password !== confirmPassword) {
      setError('Passwords do not match.');
      setLoading(false);
      return;
    }

    if (password.length < 6) {
      setError('Password is too weak. Use at least 6 characters.');
      setLoading(false);
      return;
    }

    try {
      const responseMessage = await authApi.resetPassword(token, password);
      setMessage(responseMessage);
      window.setTimeout(() => navigate('/login'), 1200);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to reset your password right now.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="theme-auth-page min-h-screen overflow-hidden px-4 py-8 md:px-8 md:py-10">
      <SeoMeta
        title="Choose new password"
        description="Set a new password for UR Academic Resource Hub."
        canonicalPath="/reset-password"
        robots="noindex,nofollow"
      />
      <div className="mx-auto grid min-h-[calc(100vh-4rem)] max-w-7xl gap-6 lg:grid-cols-[1.15fr_0.85fr]">
        <AuthShowcase />

        <div className="flex items-center justify-center">
          <div className="theme-auth-card w-full max-w-xl rounded-[2rem] p-8 md:p-10">
            <div className="mb-8">
              <p className="theme-link-accent mb-3 text-xs font-semibold uppercase tracking-[0.28em]">New password</p>
              <h1 className="theme-title text-3xl font-bold md:text-4xl">Choose a new password</h1>
              <p className="theme-muted mt-3 text-sm leading-6">
                Set a new password for your account. Reset links expire automatically for safety.
              </p>
            </div>

            <form onSubmit={handleSubmit} className="space-y-5">
              <div>
                <Label htmlFor="password" className="theme-form-label">New password</Label>
                <div className="relative mt-2">
                  <Input
                    id="password"
                    type={showPassword ? 'text' : 'password'}
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    placeholder="At least 6 characters"
                    required
                    minLength={6}
                    className="theme-form-input h-12 rounded-xl pr-12"
                  />
                  <button
                    type="button"
                    aria-label={showPassword ? 'Hide password' : 'Show password'}
                    onClick={() => setShowPassword((value) => !value)}
                    className="absolute inset-y-0 right-3 flex items-center text-muted-foreground hover:text-foreground"
                  >
                    {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
              </div>

              <div>
                <Label htmlFor="confirm-password" className="theme-form-label">Confirm password</Label>
                <div className="relative mt-2">
                  <Input
                    id="confirm-password"
                    type={showConfirmPassword ? 'text' : 'password'}
                    value={confirmPassword}
                    onChange={(event) => setConfirmPassword(event.target.value)}
                    placeholder="Re-enter your password"
                    required
                    minLength={6}
                    className="theme-form-input h-12 rounded-xl pr-12"
                  />
                  <button
                    type="button"
                    aria-label={showConfirmPassword ? 'Hide confirm password' : 'Show confirm password'}
                    onClick={() => setShowConfirmPassword((value) => !value)}
                    className="absolute inset-y-0 right-3 flex items-center text-muted-foreground hover:text-foreground"
                  >
                    {showConfirmPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
              </div>

              {error && <p className="theme-error-note rounded-xl px-4 py-3 text-sm">{error}</p>}
              {message && <p className="theme-warning-note rounded-xl px-4 py-3 text-sm">{message}</p>}

              <Button
                type="submit"
                className="theme-accent-bg h-12 w-full rounded-xl"
                disabled={loading}
              >
                {loading ? 'Updating password...' : 'Update password'}
              </Button>
            </form>

            <div className="theme-auth-subtle mt-6 rounded-2xl px-4 py-4 text-sm">
              <p>
                Need a fresh link?{' '}
                <button
                  type="button"
                  onClick={() => navigate('/forgot-password')}
                  className="theme-link-accent font-semibold underline underline-offset-4"
                >
                  Request another reset
                </button>
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

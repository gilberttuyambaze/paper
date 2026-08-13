import { FormEvent, useState } from 'react';
import { Eye, EyeOff, Loader2 } from 'lucide-react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import SeoMeta from '@/components/SeoMeta';
import GoogleSignInButton from '../components/GoogleSignInButton';
import AuthShowcase from '../components/AuthShowcase';
import { authApi } from '../lib/auth';

export default function LoginPage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const returnTo = searchParams.get('returnTo') || '/';
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showPassword, setShowPassword] = useState(false);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (loading) return;
    setLoading(true);
    setError(null);

    try {
      await authApi.loginWithCredentials(email, password);
      window.location.replace(returnTo);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed, please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="theme-auth-page min-h-screen overflow-hidden px-4 py-8 md:px-8 md:py-10">
      <SeoMeta
        title="Sign in"
        description="Private sign-in page for UR Academic Resource Hub users."
        canonicalPath="/login"
        robots="noindex,nofollow"
      />
      <div className="mx-auto grid min-h-[calc(100vh-4rem)] max-w-7xl gap-6 lg:grid-cols-[1.15fr_0.85fr]">
        <AuthShowcase />

        <div className="flex items-center justify-center">
          <div className="theme-auth-card w-full max-w-xl rounded-[2rem] p-8 md:p-10">
            <div className="mb-8">
              <p className="theme-link-accent mb-3 text-xs font-semibold uppercase tracking-[0.28em]">Welcome back</p>
              <h1 className="theme-title text-3xl font-bold md:text-4xl">Sign in to continue</h1>
              <p className="theme-muted mt-3 text-sm leading-6">
                Enter your account details to access papers, uploads, dashboards, and your saved activity.
              </p>
              <button
                type="button"
                onClick={() => navigate('/')}
                className="theme-link-accent mt-4 text-sm font-semibold underline underline-offset-4"
              >
                Back to home page
              </button>
            </div>

            <form onSubmit={handleSubmit} className="space-y-5">
              <div>
                <Label htmlFor="email" className="theme-form-label">Email</Label>
                <Input
                  id="email"
                  type="email"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  disabled={loading}
                  placeholder="you@example.com"
                  required
                  className="theme-form-input mt-2 h-12 rounded-xl"
                />
              </div>

              <div>
                <div className="flex items-center justify-between">
                  <Label htmlFor="password" className="theme-form-label">Password</Label>
                  <button
                    type="button"
                    onClick={() => navigate('/forgot-password')}
                    className="theme-link-accent text-xs font-semibold underline underline-offset-4"
                  >
                    Forgot password?
                  </button>
                </div>
                <div className="relative mt-2">
                  <Input
                    id="password"
                    type={showPassword ? 'text' : 'password'}
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    disabled={loading}
                    placeholder="Enter your password"
                    required
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

              {error && <p className="theme-error-note rounded-xl px-4 py-3 text-sm">{error}</p>}

              <Button
                type="submit"
                className="theme-accent-bg h-12 w-full rounded-xl hover:bg-black"
                disabled={loading}
              >
                {loading ? <span className="flex items-center gap-2"><Loader2 className="h-4 w-4 animate-spin" />Signing in...</span> : 'Sign in'}
              </Button>

              <div className="relative">
                <div className="absolute inset-0 flex items-center">
                  <div className="w-full border-t border-border" />
                </div>
                <div className="relative flex justify-center text-xs uppercase tracking-[0.2em] text-muted-foreground">
                  <span className="bg-transparent px-2">or</span>
                </div>
              </div>

              <GoogleSignInButton
                onSuccess={async (credential) => {
                  if (loading) return;
                  setLoading(true);
                  setError(null);
                  try {
                    const token = await authApi.loginWithGoogle(credential);
                    if (token) window.location.replace(returnTo);
                  } catch (err) {
                    setError(err instanceof Error ? err.message : 'Google sign-in failed. Please try again.');
                  } finally {
                    setLoading(false);
                  }
                }}
                onError={(message) => setError(message)}
                disabled={loading}
              />
            </form>

            <div className="theme-auth-subtle mt-6 rounded-2xl px-4 py-4 text-sm">
              <p>
                New here?{' '}
                <button
                  type="button"
                  onClick={() => navigate(`/register?returnTo=${encodeURIComponent(returnTo)}`)}
                  className="theme-link-accent font-semibold underline underline-offset-4"
                >
                  Create an account
                </button>
              </p>
              <p className="theme-muted mt-2 text-xs">You will be returned to your previous page after signing in.</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

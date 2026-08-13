import { useEffect, useRef, useState } from 'react';
import { Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { ensureGoogleGsiReady } from '@/lib/googleGsi';

declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize: (options: Record<string, unknown>) => void;
          prompt: (callback?: (notification: { isNotDisplayed: () => boolean; isSkippedMoment: () => boolean }) => void) => void;
        };
      };
    };
  }
}

type GoogleSignInButtonProps = {
  onSuccess: (credential: string) => void | Promise<void>;
  onError?: (message: string) => void;
  label?: string;
  disabled?: boolean;
  className?: string;
};

export default function GoogleSignInButton({
  onSuccess,
  onError,
  label = 'Continue with Google',
  disabled = false,
  className = '',
}: GoogleSignInButtonProps) {
  const [isReady, setIsReady] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const loadingRef = useRef(false);

  const finishLoading = () => {
    loadingRef.current = false;
    setIsLoading(false);
  };

  const reportError = (message: string) => {
    finishLoading();
    onError?.(message);
  };

  useEffect(() => {
    const clientId = import.meta.env.VITE_GOOGLE_CLIENT_ID;
    if (!clientId) {
      setIsReady(false);
      onError?.('Google Sign-In is temporarily unavailable because this site has not completed its Google configuration.');
      return;
    }

    let isCancelled = false;

    const initializeGoogle = async () => {
      try {
        const ready = await ensureGoogleGsiReady(clientId, async (response: { credential?: string }) => {
          if (!response?.credential) {
            reportError('Google sign-in was cancelled.');
            return;
          }

          if (!loadingRef.current) {
            loadingRef.current = true;
            setIsLoading(true);
          }
          try {
            await onSuccess(response.credential);
          } catch (error) {
            reportError(error instanceof Error ? error.message : 'Google sign-in failed. Please try again.');
          } finally {
            finishLoading();
          }
        });

        if (!isCancelled) {
          setIsReady(Boolean(ready));
        }
      } catch {
        if (!isCancelled) {
          setIsReady(false);
        }
      }
    };

    void initializeGoogle();

    return () => {
      isCancelled = true;
    };
  }, [onError, onSuccess]);

  const handleClick = () => {
    if (disabled || isLoading || loadingRef.current) return;
    const clientId = import.meta.env.VITE_GOOGLE_CLIENT_ID;
    if (!clientId) {
      reportError('Google Sign-In is temporarily unavailable because this site has not completed its Google configuration.');
      return;
    }

    if (!window.google?.accounts?.id) {
      reportError('Google Sign-In is not available right now. Please try again or use your email and password.');
      return;
    }

    loadingRef.current = true;
    setIsLoading(true);
    window.google.accounts.id.prompt((notification) => {
      if (notification.isNotDisplayed() || notification.isSkippedMoment()) {
        reportError('Google sign-in is not available right now. Please try again or use your email and password.');
      }
    });
  };

  return (
    <Button
      type="button"
      variant="outline"
      onClick={handleClick}
      disabled={disabled || isLoading || !isReady}
      className={`h-12 w-full rounded-xl border border-border bg-card text-card-foreground shadow-sm hover:bg-black ${className}`}
    >
      <span className="flex items-center justify-center gap-3">
        <span className="flex h-7 w-7 items-center justify-center rounded-full bg-secondary text-sm font-bold text-secondary-foreground">
          G
        </span>
        {isLoading && <Loader2 className="h-4 w-4 animate-spin" />}
        <span>{isLoading ? 'Signing in with Google...' : label}</span>
      </span>
    </Button>
  );
}

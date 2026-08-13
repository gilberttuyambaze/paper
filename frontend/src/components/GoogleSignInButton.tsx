import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';

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

  useEffect(() => {
    const clientId = import.meta.env.VITE_GOOGLE_CLIENT_ID;
    if (!clientId) {
      onError?.('Google Sign-In is not configured.');
      return;
    }

    const existingScript = document.getElementById('google-gsi-script') as HTMLScriptElement | null;

    const initializeGoogle = () => {
      if (!window.google?.accounts?.id) {
        setIsReady(false);
        return;
      }

      window.google.accounts.id.initialize({
        client_id: clientId,
        callback: async (response: { credential?: string }) => {
          if (!response?.credential) {
            onError?.('Google sign-in was cancelled.');
            return;
          }

          setIsLoading(true);
          try {
            await onSuccess(response.credential);
          } finally {
            setIsLoading(false);
          }
        },
        auto_select: false,
        cancel_on_tap_outside: true,
      });

      setIsReady(true);
    };

    if (existingScript) {
      if (window.google?.accounts?.id) {
        initializeGoogle();
      } else {
        existingScript.addEventListener('load', initializeGoogle, { once: true });
      }
      return;
    }

    const script = document.createElement('script');
    script.id = 'google-gsi-script';
    script.src = 'https://accounts.google.com/gsi/client';
    script.async = true;
    script.defer = true;
    script.onload = initializeGoogle;
    document.body.appendChild(script);

    return () => {
      script.onload = null;
    };
  }, [onError, onSuccess]);

  const handleClick = () => {
    const clientId = import.meta.env.VITE_GOOGLE_CLIENT_ID;
    if (!clientId) {
      onError?.('Google Sign-In is not configured.');
      return;
    }

    if (!window.google?.accounts?.id) {
      onError?.('Google Sign-In is not available right now.');
      return;
    }

    window.google.accounts.id.prompt((notification) => {
      if (notification.isNotDisplayed() || notification.isSkippedMoment()) {
        onError?.('Google sign-in is not available right now. Please try again or use your email and password.');
      }
    });
  };

  return (
    <Button
      type="button"
      variant="outline"
      onClick={handleClick}
      disabled={disabled || isLoading || !isReady}
      className={`h-12 w-full rounded-xl border border-slate-200 bg-white text-slate-800 shadow-sm hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100 ${className}`}
    >
      <span className="flex items-center justify-center gap-3">
        <span className="flex h-7 w-7 items-center justify-center rounded-full bg-slate-100 text-sm font-bold text-slate-700 dark:bg-slate-800 dark:text-slate-200">
          G
        </span>
        <span>{isLoading ? 'Signing in...' : label}</span>
      </span>
    </Button>
  );
}

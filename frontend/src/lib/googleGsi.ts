type GoogleGsiCallback = (response: { credential?: string }) => void | Promise<void>;

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

let gsiInitializationPromise: Promise<boolean> | null = null;
let gsiClientId: string | null = null;
let gsiCallback: GoogleGsiCallback | null = null;

export async function ensureGoogleGsiReady(clientId: string, callback: GoogleGsiCallback): Promise<boolean> {
  if (!clientId) {
    return false;
  }

  gsiCallback = callback;

  if (gsiInitializationPromise && gsiClientId === clientId) {
    return gsiInitializationPromise;
  }

  gsiClientId = clientId;

  gsiInitializationPromise = new Promise((resolve) => {
    const existingScript = document.getElementById('google-gsi-script') as HTMLScriptElement | null;

    const finish = () => {
      if (!window.google?.accounts?.id) {
        resolve(false);
        return;
      }

      window.google.accounts.id.initialize({
        client_id: clientId,
        // This stable dispatcher means React StrictMode, route changes, and
        // multiple mounted buttons update the active callback without calling
        // Google initialize again.
        callback: (response: { credential?: string }) => {
          void gsiCallback?.(response);
        },
        auto_select: false,
        cancel_on_tap_outside: true,
      });
      resolve(true);
    };

    if (window.google?.accounts?.id) {
      finish();
      return;
    }

    if (existingScript) {
      existingScript.addEventListener('load', finish, { once: true });
      return;
    }

    const script = document.createElement('script');
    script.id = 'google-gsi-script';
    script.src = 'https://accounts.google.com/gsi/client';
    script.async = true;
    script.defer = true;
    script.onload = finish;
    script.onerror = () => resolve(false);
    document.body.appendChild(script);
  });

  return gsiInitializationPromise;
}

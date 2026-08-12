export interface RuntimeConfig {
  API_BASE_URL: string;
}

let runtimeConfig: RuntimeConfig | null = null;
let configLoading = true;

const defaultConfig: RuntimeConfig = {
  API_BASE_URL: '',
};

const CONFIG_TIMEOUT_MS = 2500;
const CONFIG_TIMEOUT_REASON = 'runtime-config-timeout';

export function getDefaultConfig(): RuntimeConfig {
  if (import.meta.env.VITE_API_BASE_URL) {
    return {
      API_BASE_URL: import.meta.env.VITE_API_BASE_URL,
    };
  }

  return defaultConfig;
}

export function applyRuntimeConfig(config: RuntimeConfig) {
  runtimeConfig = config;
  configLoading = false;
}

export function markRuntimeConfigResolved() {
  configLoading = false;
}

export async function loadRuntimeConfig(timeoutMs = CONFIG_TIMEOUT_MS): Promise<RuntimeConfig> {
  const fallback = getDefaultConfig();

  try {
    // A deployed split frontend already has a safe, explicit backend URL at build
    // time. Avoid a blocking runtime probe (and a second same-origin fallback
    // probe) before the application can render.
    if (fallback.API_BASE_URL) {
      applyRuntimeConfig(fallback);
      return fallback;
    }

    const envApiBaseUrl = import.meta.env.VITE_API_BASE_URL;
    const configUrls: string[] = [];

    if (envApiBaseUrl) {
      configUrls.push(`${envApiBaseUrl.replace(/\/$/, '')}/api/config`);
    }

    if (typeof window !== 'undefined') {
      configUrls.push('/api/config');
    }

    const uniqueConfigUrls = Array.from(new Set(configUrls));

    if (uniqueConfigUrls.length === 0) {
      applyRuntimeConfig(fallback);
      return fallback;
    }

    for (const configUrl of uniqueConfigUrls) {
      const controller = new AbortController();
      const timeout = window.setTimeout(() => controller.abort(CONFIG_TIMEOUT_REASON), timeoutMs);

      try {
        const response = await fetch(configUrl, {
          signal: controller.signal,
        });
        const contentType = response.headers.get('content-type') || '';

        if (response.ok && contentType.includes('application/json')) {
          const loadedConfig = (await response.json()) as RuntimeConfig;
          applyRuntimeConfig(loadedConfig);
          return loadedConfig;
        }

        console.warn(`Runtime config endpoint ${configUrl} returned a non-JSON or non-OK response`);
      } catch (error) {
        if (error instanceof DOMException && error.name === 'AbortError') {
          console.warn(`Runtime config request to ${configUrl} timed out after ${timeoutMs}ms`);
        } else {
          console.warn(`Runtime config request to ${configUrl} failed:`, error);
        }
      } finally {
        window.clearTimeout(timeout);
      }
    }

    if (!fallback.API_BASE_URL && typeof window !== 'undefined' && !isLocalFrontendDevOrigin(window.location.origin)) {
      console.error(
        'No production API base URL was resolved. Set VITE_API_BASE_URL for split frontend/backend deploys or expose /api/config on the deployed origin.'
      );
    }

    applyRuntimeConfig(fallback);
    return fallback;
  } catch (error) {
    console.warn('Runtime config discovery failed, using fallback config:', error);
    applyRuntimeConfig(fallback);
    return fallback;
  } finally {
    markRuntimeConfigResolved();
  }
}

export function getConfig() {
  if (configLoading) {
    return getDefaultConfig();
  }

  if (runtimeConfig) {
    return runtimeConfig;
  }

  return getDefaultConfig();
}

function isLocalFrontendDevOrigin(origin: string): boolean {
  try {
    const url = new URL(origin);
    return ['localhost', '127.0.0.1', '0.0.0.0'].includes(url.hostname);
  } catch {
    return false;
  }
}

function isLocalBackendUrl(apiBaseUrl: string): boolean {
  try {
    const url = new URL(apiBaseUrl);
    return (
      ['localhost', '127.0.0.1', '0.0.0.0'].includes(url.hostname) &&
      url.port === '8000'
    );
  } catch {
    return false;
  }
}

function shouldUseLocalProxy(apiBaseUrl: string): boolean {
  if (typeof window === 'undefined') return false;
  if (!isLocalFrontendDevOrigin(window.location.origin)) return false;

  return isLocalBackendUrl(apiBaseUrl);
}

export function getAPIBaseURL(): string {
  const apiBaseUrl = getConfig().API_BASE_URL;

  // In local Vite development, prefer the same-origin `/api` proxy so popup auth
  // and token exchange avoid unnecessary cross-origin browser restrictions.
  if (shouldUseLocalProxy(apiBaseUrl)) {
    return '';
  }

  return apiBaseUrl;
}

export const config = {
  get API_BASE_URL() {
    return getAPIBaseURL();
  },
};

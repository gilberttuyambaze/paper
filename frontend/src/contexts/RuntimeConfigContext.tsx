import React, { createContext, useContext, useEffect, useMemo, useState } from 'react';
import AppStartupScreen from '@/components/AppStartupScreen';
import {
  getDefaultConfig,
  loadRuntimeConfig,
  type RuntimeConfig,
} from '@/lib/config';

type RuntimeConfigStatus = 'loading' | 'ready';

interface RuntimeConfigContextValue {
  config: RuntimeConfig;
  status: RuntimeConfigStatus;
  isFallbackConfig: boolean;
}

const RuntimeConfigContext = createContext<RuntimeConfigContextValue | null>(null);

export function useRuntimeConfig() {
  const context = useContext(RuntimeConfigContext);
  if (!context) {
    throw new Error('useRuntimeConfig must be used within a RuntimeConfigProvider');
  }
  return context;
}

interface RuntimeConfigProviderProps {
  children: React.ReactNode;
}

export function RuntimeConfigProvider({
  children,
}: RuntimeConfigProviderProps) {
  const [config, setConfig] = useState<RuntimeConfig>(() => getDefaultConfig());
  const [status, setStatus] = useState<RuntimeConfigStatus>(() =>
    getDefaultConfig().API_BASE_URL ? 'ready' : 'loading'
  );
  const [isFallbackConfig, setIsFallbackConfig] = useState(false);

  useEffect(() => {
    let active = true;
    const fallback = getDefaultConfig();

    const initialize = async () => {
      try {
        const loadedConfig = await loadRuntimeConfig();
        if (!active) return;
        setConfig(loadedConfig);
        setIsFallbackConfig(loadedConfig.API_BASE_URL === fallback.API_BASE_URL);
      } catch (error) {
        if (!active) return;
        console.warn('Runtime config load failed, using fallback config:', error);
        setConfig(fallback);
        setIsFallbackConfig(true);
      } finally {
        if (!active) return;
        setStatus('ready');
      }
    };

    void initialize();

    return () => {
      active = false;
    };
  }, []);

  const value = useMemo(
    () => ({
      config,
      status,
      isFallbackConfig,
    }),
    [config, status, isFallbackConfig]
  );

  return (
    <RuntimeConfigContext.Provider value={value}>
      <div className="app-bootstrap-shell">
        {status === 'ready' ? children : null}
        <AppStartupScreen status={status} />
      </div>
    </RuntimeConfigContext.Provider>
  );
}

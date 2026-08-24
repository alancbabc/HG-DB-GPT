import {
  DEFAULT_UI_VISIBILITY,
  UI_VISIBILITY_CONFIG_URL,
  UiVisibilityConfig,
  resolveUiVisibilityConfig,
} from '@/config/ui-visibility';
import React, { createContext, useContext, useEffect, useMemo, useState } from 'react';

interface UiVisibilityContextValue {
  config: UiVisibilityConfig;
  ready: boolean;
}

const UiVisibilityContext = createContext<UiVisibilityContextValue>({
  config: DEFAULT_UI_VISIBILITY,
  ready: false,
});

export function UiVisibilityProvider({ children }: { children: React.ReactNode }) {
  const [config, setConfig] = useState<UiVisibilityConfig>(DEFAULT_UI_VISIBILITY);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort(), 3000);

    fetch(UI_VISIBILITY_CONFIG_URL, { cache: 'no-store', signal: controller.signal })
      .then(response => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.json();
      })
      .then(value => {
        if (active) setConfig(resolveUiVisibilityConfig(value));
      })
      .catch(error => {
        console.warn('Unable to load UI visibility config; using visible defaults.', error);
      })
      .finally(() => {
        window.clearTimeout(timeoutId);
        if (active) setReady(true);
      });

    return () => {
      active = false;
      window.clearTimeout(timeoutId);
      controller.abort();
    };
  }, []);

  const value = useMemo(() => ({ config, ready }), [config, ready]);
  return <UiVisibilityContext.Provider value={value}>{children}</UiVisibilityContext.Provider>;
}

export function useUiVisibility(): UiVisibilityContextValue {
  return useContext(UiVisibilityContext);
}

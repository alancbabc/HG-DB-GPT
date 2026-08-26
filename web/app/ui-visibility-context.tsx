import {
  DEFAULT_UI_VISIBILITY,
  UI_VISIBILITY_CONFIG_URL,
  UiVisibilityConfig,
  UI_VISIBILITY_CACHE_KEY,
  resolveUiVisibilityConfig,
} from '@/config/ui-visibility';
import React, { createContext, useContext, useEffect, useMemo, useState } from 'react';

interface UiVisibilityContextValue {
  config: UiVisibilityConfig;
  ready: boolean;
}

function readCachedConfig(): UiVisibilityConfig | null {
  if (typeof window === 'undefined') return null;
  try {
    const cached = window.sessionStorage.getItem(UI_VISIBILITY_CACHE_KEY);
    if (!cached) return null;
    const value: unknown = JSON.parse(cached);
    if (typeof value !== 'object' || value === null || Array.isArray(value)) return null;
    if (!('version' in value) || value.version !== 1) return null;
    return resolveUiVisibilityConfig(value);
  } catch {
    return null;
  }
}

const UiVisibilityContext = createContext<UiVisibilityContextValue>({
  config: DEFAULT_UI_VISIBILITY,
  ready: false,
});

export function UiVisibilityProvider({ children }: { children: React.ReactNode }) {
  const [config, setConfig] = useState<UiVisibilityConfig>(() => readCachedConfig() ?? DEFAULT_UI_VISIBILITY);
  const [ready, setReady] = useState(() => readCachedConfig() !== null);

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
        if (active) {
          const resolved = resolveUiVisibilityConfig(value);
          setConfig(resolved);
          try {
            window.sessionStorage.setItem(UI_VISIBILITY_CACHE_KEY, JSON.stringify(resolved));
          } catch {
            // Storage can be unavailable in private browsing or restricted WebViews.
          }
        }
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

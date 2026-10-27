/// <reference types="vite/client" />

// Tauri bridge present only when the webapp runs inside the launcher shell
// (WKWebView). Injected by the shell, not by any bundler — declared here so
// components can feature-detect (plain browsers have no __TAURI__).
interface Window {
  __TAURI__?: {
    core: { invoke: <T>(cmd: string, args?: Record<string, unknown>): Promise<T> };
  };
}

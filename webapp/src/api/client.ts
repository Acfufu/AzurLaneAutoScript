import type { ArgSchema, MenuSchema, Status } from "./types";
import { reportApiError } from "./errors.svelte";

/**
 * Base URL of the python backend.
 * Empty means same origin (production: served by the backend itself,
 * or the Tauri shell which loads the page from the backend).
 * Overridable via VITE_API_BASE for the vite dev server.
 */
const BASE = import.meta.env.VITE_API_BASE ?? "";

async function request<T>(path: string, init?: RequestInit, timeoutMs = 30000): Promise<T> {
  let res: Response;
  try {
    // Default timeout so a hung backend can't leave a saving indicator
    // spinning forever (audit L12). Callers passing their own signal (none
    // today) keep it.
    res = await fetch(`${BASE}${path}`, { ...init, signal: init?.signal ?? AbortSignal.timeout(timeoutMs) });
  } catch (e) {
    if (e instanceof DOMException && e.name === "TimeoutError") {
      reportApiError(`Request timeout: ${path}`);
      throw e;
    }
    reportApiError(`Network error: ${path}`);
    throw e;
  }
  if (!res.ok) {
    reportApiError(`${path} → ${res.status}`);
    throw new Error(`${path} -> ${res.status}`);
  }
  try {
    return (await res.json()) as T;
  } catch (e) {
    reportApiError(`Bad response: ${path}`);
    throw e;
  }
}

export const api = {
  status: () => request<Status>("/status"),

  schema: (mod = "alas", instance?: string) =>
    request<{ menu: MenuSchema; args: ArgSchema }>(
      `/schema/${mod}${instance ? `?instance=${encodeURIComponent(instance)}` : ""}`,
    ),

  config: (name: string) => request<Record<string, unknown>>(`/config/${name}`),

  saveConfig: (name: string, values: Record<string, unknown>) =>
    request<{ valid: string[]; invalid: string[] }>(`/config/${name}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ value: values }),
    }),

  i18n: (lang: string) => request<Record<string, string>>(`/i18n/${lang}`),

  setLanguage: (language: string) =>
    request<{ language: string }>("/language", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ language }),
    }),

  setTheme: (theme: string) =>
    request<{ theme: string }>("/theme", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ theme }),
    }),

  run: (instance: string, func?: string) =>
    request<{ ok: boolean; error?: string }>("/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ instance, func }),
    }),

  stop: (instance: string) =>
    request<{ ok: boolean }>("/stop", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ instance }),
    }),

  newInstance: (name: string, origin?: string) =>
    request<{ ok: boolean; error?: string }>("/instance/new", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, origin }),
    }),

  deleteInstance: (name: string) =>
    request<{ ok: boolean; error?: string }>("/instance/delete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    }),

  renameInstance: (name: string, newName: string) =>
    request<{ ok: boolean; error?: string }>("/instance/rename", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, new_name: newName }),
    }),

  importConfig: (name: string, config: Record<string, unknown>) =>
    request<{ ok: boolean }>(`/config/${encodeURIComponent(name)}/import`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ config }),
    }),

  /** Raw file download — goes through fetch (not request) because the
   *  payload is a blob, but still checks res.ok so a redirect-to-HTML or
   *  404 body can't be saved as "{name}.json" (audit M6). */
  exportConfig: async (name: string): Promise<Blob> => {
    const res = await fetch(`${BASE}/config/${encodeURIComponent(name)}/export`);
    if (!res.ok) {
      throw new Error(`Export failed: ${res.status}`);
    }
    return res.blob();
  },

  updateStatus: () =>
    request<{
      current: string;
      repo: string;
      mode: "release" | "git";
      state: string;
      error: string | null;
      releases: {
        tag: string;
        name: string;
        body: string;
        date: string;
        prerelease: boolean;
        assets: { name: string; size: number; url: string }[];
      }[];
      installing: { version: string; stage: string; progress: number } | null;
      git: {
        branch: string;
        state: string;
        error: string | null;
        commits: { sha: string; date: string; message: string }[];
      };
    }>("/update/status"),

  configs: () => request<{ name: string; modified: string }[]>("/configs"),

  updateRefresh: () => request<{ ok: boolean }>("/update/refresh", { method: "POST" }),

  /** Ask the launcher to pull + restart the backend (git mode only). */
  updateRestart: () => request<{ ok: boolean; error?: string }>("/update/restart", { method: "POST" }),

  updateInstall: (version: string) =>
    request<{ ok: boolean; error?: string }>("/update/install", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ version }),
    }),

  remoteStatus: () => request<{ alive: boolean; state: string; entry_point: string }>("/remote/status"),

  remoteStart: () => request<{ ok: boolean }>("/remote/start", { method: "POST" }),

  remoteStop: () => request<{ ok: boolean }>("/remote/stop", { method: "POST" }),

  scheduler: (name: string) =>
    request<{
      alive: boolean;
      running_func: string | null;
      pending: { command: string; next_run: string }[];
      waiting: { command: string; next_run: string }[];
    }>(`/scheduler/${name}`),
};

export type { Status };

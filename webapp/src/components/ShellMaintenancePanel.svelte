<script lang="ts">
import { status } from "../api/store.svelte";

/** Launcher-shell maintenance settings (direction-7a): log/error-screenshot
 *  retention numbers, enforced by the launcher's log-cleanup thread. Same
 *  family as EmulatorPanel — rendered ONLY inside the launcher webview
 *  (window.__TAURI__ bridge), a plain LAN/remote browser never sees it;
 *  strings are a local 4-language dictionary so payload i18n files stay
 *  untouched (daily upstream merge stays conflict-free). */
const shell = typeof window !== "undefined" && window.__TAURI__ !== undefined;

interface CleanupPolicy {
  retentionDays: number;
  sizeLimitGb: number;
}

const DICTS = {
  "zh-CN": {
    title: "外壳设置",
    retention: "日志保留天数",
    sizeLimit: "日志体积上限（GB）",
    unlimited: "0 = 不限",
    apply: "应用",
    saved: "已应用",
    busy: "处理中…",
    scope: "作用于 log/（日志与错误截图），应用后立即清理一次",
    errors: {
      "days-out-of-range": "天数超出范围（0–3650）",
      "gb-out-of-range": "体积超出范围（0–100000）",
    } as Record<string, string>,
  },
  "zh-TW": {
    title: "外殼設定",
    retention: "日誌保留天數",
    sizeLimit: "日誌體積上限（GB）",
    unlimited: "0 = 不限",
    apply: "套用",
    saved: "已套用",
    busy: "處理中…",
    scope: "作用於 log/（日誌與錯誤截圖），套用後立即清理一次",
    errors: {
      "days-out-of-range": "天數超出範圍（0–3650）",
      "gb-out-of-range": "體積超出範圍（0–100000）",
    } as Record<string, string>,
  },
  "en-US": {
    title: "Shell Settings",
    retention: "Keep logs for (days)",
    sizeLimit: "Log size budget (GB)",
    unlimited: "0 = unlimited",
    apply: "Apply",
    saved: "Applied",
    busy: "Working…",
    scope: "Applies to log/ (logs + error screenshots); one cleanup pass runs immediately",
    errors: {
      "days-out-of-range": "Days out of range (0–3650)",
      "gb-out-of-range": "Size out of range (0–100000)",
    } as Record<string, string>,
  },
  "ja-JP": {
    title: "シェル設定",
    retention: "ログ保持日数",
    sizeLimit: "ログ容量上限（GB）",
    unlimited: "0 = 無制限",
    apply: "適用",
    saved: "適用済み",
    busy: "処理中…",
    scope: "log/（ログ・エラースクリーンショット）に適用、適用後すぐに1回クリーンアップします",
    errors: {
      "days-out-of-range": "日数が範囲外です（0–3650）",
      "gb-out-of-range": "容量が範囲外です（0–100000）",
    } as Record<string, string>,
  },
} as const;

type Dict = {
  title: string;
  retention: string;
  sizeLimit: string;
  unlimited: string;
  apply: string;
  saved: string;
  busy: string;
  scope: string;
  errors: Record<string, string>;
};

const L: Dict = $derived(
  (DICTS as Record<string, Dict>)[status.language] ?? DICTS["zh-CN"],
);

let loaded = $state(false);
let days = $state(14);
let gb = $state(5);
let busy = $state(false);
let savedFlash = $state(false);
let error = $state("");

async function load() {
  const tauri = window.__TAURI__;
  if (!tauri) return;
  try {
    const policy = await tauri.core.invoke<CleanupPolicy>("cleanup_get");
    days = policy.retentionDays;
    gb = policy.sizeLimitGb;
    loaded = true;
  } catch {
    // Old launcher shell without the commands: keep the panel hidden.
    loaded = false;
  }
}

async function apply() {
  const tauri = window.__TAURI__;
  if (!tauri) return;
  error = "";
  savedFlash = false;
  busy = true;
  try {
    const policy = await tauri.core.invoke<CleanupPolicy>("cleanup_set", {
      retentionDays: Math.max(0, Math.floor(days)),
      sizeLimitGb: Math.max(0, gb),
    });
    days = policy.retentionDays;
    gb = policy.sizeLimitGb;
    savedFlash = true;
    setTimeout(() => (savedFlash = false), 2000);
  } catch (e) {
    error = L.errors[String(e)] ?? String(e);
  } finally {
    busy = false;
  }
}

$effect(() => {
  if (!shell) return;
  void load();
});
</script>

{#if shell && loaded}
  <section class="panel m-1.25 flex-shrink-0 p-2.5 font-medium">
    <div class="mx-2.5 text-[1.25rem] font-medium">{L.title}</div>
    <hr class="my-1 border-0 bg-surface-hr [border-top:var(--hr-line)]" />
    <div class="mx-2.5 grid gap-1.5">
      <label class="grid items-center gap-1 [grid-template-columns:1fr_auto]">
        <span class="text-base">{L.retention}</span>
        <input
          type="number"
          min="0"
          max="3650"
          bind:value={days}
          class="w-24 border-toggle bg-surface-app px-2 py-1 text-right text-body"
        />
      </label>
      <label class="grid items-center gap-1 [grid-template-columns:1fr_auto]">
        <span class="text-base">{L.sizeLimit}</span>
        <input
          type="number"
          min="0"
          max="100000"
          step="0.5"
          bind:value={gb}
          class="w-24 border-toggle bg-surface-app px-2 py-1 text-right text-body"
        />
      </label>
      <div class="text-[0.8rem] text-muted">{L.unlimited} · {L.scope}</div>
      <div class="grid [grid-template-columns:auto_1fr] items-center gap-2">
        <button class="btn m-0 border-toggle bg-accent text-white" disabled={busy} onclick={() => apply()}>
          {busy ? L.busy : savedFlash ? L.saved : L.apply}
        </button>
        {#if error}
          <div class="text-[0.8rem] text-status-warning [overflow-wrap:anywhere]">{error}</div>
        {/if}
      </div>
    </div>
  </section>
{/if}

<script lang="ts">
import { status } from "../api/store.svelte";

interface AvdStatus {
  name: string;
  running: boolean;
  serial: string | null;
  pinnedPort: number | null;
  blocked: string | null;
}
interface FleetStatus {
  tier: string;
  maaendPresent: boolean;
  avds: AvdStatus[];
}

/** Launcher-shell emulator panel (direction-1 minimal loop). Rendered ONLY
 *  inside the launcher webview: a plain browser (LAN/remote) has no
 *  __TAURI__ bridge, so the panel — status included — is local by
 *  construction. Strings are a local dictionary (not gui.yaml t()): this is
 *  launcher-shell UI like the tray/menu labels, and payload i18n files stay
 *  untouched to keep the daily upstream merge conflict-free. Reason codes
 *  mirror src/emulators.rs (single source of truth). */
const shell = typeof window !== "undefined" && window.__TAURI__ !== undefined;

const DICTS = {
  "zh-CN": {
    title: "模拟器",
    start: "启动",
    stop: "停止",
    running: "运行中",
    stopped: "已停止",
    busy: "处理中…",
    maaendHint: "MaaEnd 在场：按互斥规则仅 Endfield 可启动",
    errors: {
      "read-only": "只读模式，启动被禁用",
      "maaend-mutex": "MaaEnd 在场，互斥拦截",
      "already-running": "已在运行",
      "not-running": "未在运行",
      busy: "操作进行中",
      "no-such-avd": "AVD 不存在",
      "emulator-binary-missing": "找不到 emulator 可执行文件",
      "spawn-failed": "启动进程失败",
      "adb-failed": "adb 操作失败",
    },
  },
  "zh-TW": {
    title: "模擬器",
    start: "啟動",
    stop: "停止",
    running: "運行中",
    stopped: "已停止",
    busy: "處理中…",
    maaendHint: "MaaEnd 在場：按互斥規則僅 Endfield 可啟動",
    errors: {
      "read-only": "唯讀模式，啟動被停用",
      "maaend-mutex": "MaaEnd 在場，互斥攔截",
      "already-running": "已在運行",
      "not-running": "未在運行",
      busy: "操作進行中",
      "no-such-avd": "AVD 不存在",
      "emulator-binary-missing": "找不到 emulator 執行檔",
      "spawn-failed": "啟動處理序失敗",
      "adb-failed": "adb 操作失敗",
    },
  },
  "en-US": {
    title: "Emulators",
    start: "Start",
    stop: "Stop",
    running: "running",
    stopped: "stopped",
    busy: "Working…",
    maaendHint: "MaaEnd present: only Endfield may start (mutex rule)",
    errors: {
      "read-only": "Read-only mode: start disabled",
      "maaend-mutex": "Blocked by the MaaEnd mutex rule",
      "already-running": "Already running",
      "not-running": "Not running",
      busy: "Another operation is in flight",
      "no-such-avd": "No such AVD",
      "emulator-binary-missing": "emulator binary not found",
      "spawn-failed": "process spawn failed",
      "adb-failed": "adb operation failed",
    },
  },
  "ja-JP": {
    title: "エミュレーター",
    start: "起動",
    stop: "停止",
    running: "実行中",
    stopped: "停止中",
    busy: "処理中…",
    maaendHint: "MaaEnd が稼働中：相互排他ルールにより Endfield のみ起動可",
    errors: {
      "read-only": "読み取り専用モードのため起動できません",
      "maaend-mutex": "MaaEnd 相互排他ルールによりブロック",
      "already-running": "既に実行中です",
      "not-running": "実行していません",
      busy: "別の操作が進行中です",
      "no-such-avd": "AVD が見つかりません",
      "emulator-binary-missing": "emulator 実行ファイルが見つかりません",
      "spawn-failed": "プロセス起動に失敗しました",
      "adb-failed": "adb 操作に失敗しました",
    },
  },
} as const;

let fleet = $state<FleetStatus | null>(null);
let busy = $state("");
let actionError = $state("");

type Dict = {
  title: string;
  start: string;
  stop: string;
  running: string;
  stopped: string;
  busy: string;
  maaendHint: string;
  errors: Record<string, string>;
};

const L: Dict = $derived(
  (DICTS as Record<string, Dict>)[status.language] ?? DICTS["zh-CN"],
);

function reasonText(code: string): string {
  return L.errors[code] ?? code;
}

async function refresh() {
  const tauri = window.__TAURI__;
  if (!tauri) return;
  try {
    fleet = await tauri.core.invoke<FleetStatus>("emu_list");
  } catch {
    // The running launcher predates the commands (old shell, new webapp):
    // keep the panel hidden instead of erroring on every poll.
    fleet = null;
  }
}

async function act(name: string, cmd: "emu_start" | "emu_stop") {
  const tauri = window.__TAURI__;
  if (!tauri) return;
  actionError = "";
  busy = name;
  try {
    await tauri.core.invoke(cmd, { name });
    // Give qemu/adb a beat to show up before the next snapshot.
    await new Promise((resolve) => setTimeout(resolve, 800));
    await refresh();
  } catch (e) {
    actionError = reasonText(String(e));
  } finally {
    busy = "";
  }
}

$effect(() => {
  if (!shell) return;
  void refresh();
  const timer = setInterval(() => void refresh(), 5000);
  return () => clearInterval(timer);
});
</script>

{#if shell && fleet}
  <section class="panel m-1.25 max-h-52 flex-shrink-0 overflow-y-auto p-2.5 font-medium">
    <div class="mx-2.5 text-[1.25rem] font-medium">{L.title}</div>
    <hr class="my-1 border-0 bg-surface-hr [border-top:var(--hr-line)]" />
    <div class="grid gap-1">
      {#if fleet.maaendPresent}
        <div class="mx-1 text-[0.8rem] text-status-warning">{L.maaendHint}</div>
      {/if}
      {#each fleet.avds as avd (avd.name)}
        <div class="my-0.5 ml-1.5 mr-2.5 grid items-center [grid-template-columns:1fr_auto]">
          <div class="min-w-0">
            <span class="mx-1 text-base [overflow-wrap:break-word]">{avd.name}</span>
            <span class="ml-1 text-[0.8rem] {avd.running ? 'text-status-running' : 'text-muted'}">
              {avd.running ? L.running : L.stopped}{avd.serial ? ` · ${avd.serial}` : ""}
            </span>
            {#if avd.blocked}
              <div class="mx-1 text-[0.8rem] text-status-warning [overflow-wrap:anywhere]">
                {reasonText(avd.blocked)}
              </div>
            {/if}
          </div>
          {#if avd.running}
            <button
              class="btn m-0 border-toggle bg-surface-app text-body"
              disabled={busy !== "" || fleet.tier === "readonly"}
              onclick={() => act(avd.name, "emu_stop")}
            >
              {busy === avd.name ? L.busy : L.stop}
            </button>
          {:else}
            <button
              class="btn m-0 border-toggle"
              class:bg-accent={!avd.blocked}
              class:bg-surface-app={!!avd.blocked}
              class:text-white={!avd.blocked}
              class:text-body={!!avd.blocked}
              disabled={busy !== "" || !!avd.blocked}
              onclick={() => act(avd.name, "emu_start")}
            >
              {busy === avd.name ? L.busy : L.start}
            </button>
          {/if}
        </div>
      {/each}
      {#if actionError}
        <div class="mx-1 text-[0.8rem] text-status-warning [overflow-wrap:anywhere]">{actionError}</div>
      {/if}
    </div>
  </section>
{/if}

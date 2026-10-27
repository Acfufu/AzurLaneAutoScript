<script lang="ts">
import { apiError, clearApiError } from "./api/errors.svelte";
import { connState, status } from "./api/store.svelte";
import { t } from "./api/i18n.svelte";
import { isTheme } from "./api/themes";
import AppHeader from "./components/AppHeader.svelte";
import { route } from "./router.svelte";
import Develop from "./views/Develop.svelte";
import Home from "./views/Home.svelte";
import Manage from "./views/Manage.svelte";
import Settings from "./views/Settings.svelte";

$effect(() => {
  // Single source of truth for theming: the data-theme attribute on <html>
  // selects the token block in src/styles/theme.css. No stylesheet swaps,
  // no FOUC, no cascade-order dependencies.
  document.documentElement.dataset.theme = isTheme(status.theme) ? status.theme : "default";
  // <html lang> follows the persisted language instead of the hardcoded
  // zh-CN in index.html (audit L14).
  document.documentElement.lang = status.language;
});
</script>

<div id="app" class="h-full">
  <AppHeader />
  {#if connState.everConnected && !connState.connected}
    <!-- Backend death used to freeze the UI with no signal at all: status
         stopped updating, buttons acted on stale state, and REST failures
         surfaced as scattered console errors (audit M11). -->
    <div
      class="fixed top-14 left-1/2 z-50 -translate-x-1/2 rounded border border-solid px-3 py-2 text-sm [border-color:var(--warning-line,var(--danger-line))] [background:var(--warning-bg,var(--danger-bg))] [color:var(--warning-fg,var(--danger-fg))]"
    >
      {t('Gui.Toast.BackendOffline')}
    </div>
  {/if}
  {#if apiError.text}
    <!-- Global API failure banner (transport/HTTP/JSON errors reported by
         client.request); expected ok:false errors stay inline in views. -->
    <div
      class="fixed bottom-2 right-2 z-50 max-w-96 rounded border border-solid px-3 py-2 text-sm [border-color:var(--danger-line)] [background:var(--danger-bg)] [color:var(--danger-fg)] [overflow-wrap:anywhere]"
    >
      <span>{apiError.text}</span>
      <button class="ms-2 border-0 bg-transparent p-0 [color:inherit] underline" onclick={clearApiError}>
        ✕
      </button>
    </div>
  {/if}
  <main class="h-[calc(100vh-50px)]">
    {#if route.path === '/settings'}
      <Settings />
    {:else if route.path === '/develop'}
      <Develop />
    {:else if route.path === '/manage'}
      <Manage />
    {:else}
      <Home />
    {/if}
  </main>
</div>

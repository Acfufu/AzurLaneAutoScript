<script lang="ts">
import { apiError, clearApiError } from "./api/errors.svelte";
import { status } from "./api/store.svelte";
import AppHeader from "./components/AppHeader.svelte";
import { route } from "./router.svelte";
import Develop from "./views/Develop.svelte";
import Home from "./views/Home.svelte";
import Manage from "./views/Manage.svelte";
import Settings from "./views/Settings.svelte";

const THEMES = ["default", "dark", "light", "minty", "yeti", "sketchy"];

$effect(() => {
  // Single source of truth for theming: the data-theme attribute on <html>
  // selects the token block in src/styles/theme.css. No stylesheet swaps,
  // no FOUC, no cascade-order dependencies.
  document.documentElement.dataset.theme = THEMES.includes(status.theme) ? status.theme : "default";
});
</script>

<div id="app" class="h-full">
  <AppHeader />
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

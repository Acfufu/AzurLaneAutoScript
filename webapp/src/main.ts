import "virtual:uno.css";
import "./styles/theme.css";
import "./styles/base.css";
import { mount } from "svelte";
import App from "./App.svelte";
import { loadI18n } from "./api/i18n.svelte";
import { connectEvents, refreshStatus, status } from "./api/store.svelte";
import { isTheme } from "./api/themes";
import { initRouter } from "./router.svelte";

async function bootstrap() {
  // Fetch status (theme/language) before mounting so i18n and the theme
  // initialize with the persisted settings.
  try {
    await refreshStatus();
  } catch {
    // backend not ready yet; the SSE reconnection will refresh later
  }
  // Theme is a single data-theme attribute on <html>; setting it before
  // mount avoids any flash of the default theme. Persisted values are
  // validated against the canonical theme list (audit L1).
  document.documentElement.dataset.theme = isTheme(status.theme) ? status.theme : "default";
  try {
    await loadI18n();
  } catch {
    // backend not ready yet
  }
  initRouter();
  mount(App, { target: document.getElementById("app")! });
  connectEvents();
}

void bootstrap();

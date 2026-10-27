/**
 * Global API error channel.
 *
 * `client.request` reports transport/HTTP/JSON failures here and App.svelte
 * renders a dismissible banner. Views keep their own inline messages for
 * expected `ok:false` responses; this catches the silent
 * unhandled-rejection class (backend down, 4xx/5xx, bad JSON) that
 * otherwise leaves a frozen UI with no feedback (audit M7).
 */
export const apiError = $state<{ text: string }>({ text: "" });

export function reportApiError(text: string): void {
  apiError.text = text;
}

export function clearApiError(): void {
  apiError.text = "";
}

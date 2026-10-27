/** Canonical webui themes — the blocks that actually exist in
 *  styles/theme.css (:root default + dark/minty/yeti/sketchy). Single
 *  source for App.svelte's guard, main.ts bootstrap and the Develop
 *  picker; "light" used to be offered with no stylesheet behind it, and
 *  the lists drifted across the three call sites (audit L1). */
export const THEMES = ["default", "dark", "minty", "yeti", "sketchy"] as const;

export const THEME_OPTIONS: { label: string; value: (typeof THEMES)[number] }[] = [
  { label: "Light", value: "default" },
  { label: "Dark", value: "dark" },
  { label: "Minty", value: "minty" },
  { label: "Yeti", value: "yeti" },
  { label: "Sketchy", value: "sketchy" },
];

export function isTheme(value: string): boolean {
  return (THEMES as readonly string[]).includes(value);
}

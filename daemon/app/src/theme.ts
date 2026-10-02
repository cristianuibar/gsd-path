// Appearance: follow the OS, or the choice the user made in Settings → App.
export type Theme = "system" | "light" | "dark";
const KEY = "gsd-path.theme";

/** The theme to draw for a stored choice and the OS setting. */
export const resolveTheme = (choice: string | null, osDark: boolean): "light" | "dark" =>
  choice === "light" || choice === "dark" ? choice : osDark ? "dark" : "light";

export const storedTheme = (): Theme => {
  const choice = localStorage.getItem(KEY);
  return choice === "light" || choice === "dark" ? choice : "system";
};

// Read in the functions, not at import: the tests have no window.
const osDark = () => matchMedia("(prefers-color-scheme: dark)");
export function applyTheme() {
  document.documentElement.dataset.theme = resolveTheme(localStorage.getItem(KEY), osDark().matches);
}
export function setTheme(choice: Theme) {
  if (choice === "system") localStorage.removeItem(KEY);
  else localStorage.setItem(KEY, choice);
  applyTheme();
}
/** Call once at start: draw the theme and follow later OS changes. */
export function watchTheme() {
  applyTheme();
  osDark().addEventListener("change", applyTheme);
  // The tray popover is another window; it follows a change made in Settings.
  addEventListener("storage", (event) => { if (event.key === KEY) applyTheme(); });
}

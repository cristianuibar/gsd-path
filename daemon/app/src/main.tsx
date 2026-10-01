import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import "./app.css";

// Follow the OS theme until Settings (slice A4c) lets the user choose.
const dark = matchMedia("(prefers-color-scheme: dark)");
const applyTheme = () => { document.documentElement.dataset.theme = dark.matches ? "dark" : "light"; };
applyTheme();
dark.addEventListener("change", applyTheme);

if (import.meta.env.DEV && !("__TAURI_INTERNALS__" in window)) await import("./dev-mock");

createRoot(document.getElementById("root")!).render(<StrictMode><App /></StrictMode>);

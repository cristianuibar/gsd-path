import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import "./app.css";
import { watchTheme } from "./theme";

watchTheme();

if (import.meta.env.DEV && !("__TAURI_INTERNALS__" in window)) await import("./dev-mock");

createRoot(document.getElementById("root")!).render(<StrictMode><App /></StrictMode>);

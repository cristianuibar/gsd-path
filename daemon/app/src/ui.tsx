// Small shared pieces. Screens build on these and on the classes in app.css.
import { useState } from "react";
import { openUrl } from "./shell";
import type { RowAction } from "./screen";

/** The three-chevron mark, the same as ICON.mark in the daemon dashboard. */
export function Logo({ size = 18, label = true }: { size?: number; label?: boolean }) {
  return (
    <div className="logo">
      <svg viewBox="0 0 18 18" fill="none" width={size} height={size} aria-hidden="true">
        {["M1.6 4 5.6 9 1.6 14", "M7 4 11 9 7 14", "M12.4 4 16.4 9 12.4 14"].map((d) => (
          <path key={d} d={d} stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        ))}
      </svg>
      {label && "OpenGSD Path"}
    </div>
  );
}

/** Copies text and says so on the button for a moment. */
export function CopyButton({ text, label, primary }: { text: string; label: string; primary?: boolean }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };
  return <button className={primary ? "btn primary" : "btn"} onClick={copy}>{copied ? "Copied" : label}</button>;
}

export function ActionButton({ action, primary = true }: { action: RowAction; primary?: boolean }) {
  if ("copy" in action) return <CopyButton text={action.copy} label={action.label} primary={primary} />;
  return <button className={primary ? "btn primary" : "btn"} onClick={() => openUrl(action.url)}>{action.label}</button>;
}

/** Fix text from the daemon marks commands with backticks; show them as code. */
export function FixText({ text }: { text: string }) {
  return <>{text.split("`").map((part, index) => (index % 2 ? <code key={index} className="mono">{part}</code> : part))}</>;
}

/** The first command in a fix text, for a Copy button. */
export const firstCommand = (text: string) => text.split("`")[1] ?? null;

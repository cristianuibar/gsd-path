import { describe, expect, it } from "vitest";
import { appUpdateRow, readyLine, refusedText } from "./appUpdate";
import type { Shell } from "./shell";

const shell = (over: Partial<Shell>) => ({ version: "0.1.0", update: null, update_error: null, ...over }) as Shell;

describe("app update", () => {
  it("has no row while no update is known and nothing failed", () => {
    expect(appUpdateRow(shell({}))).toBeNull();
  });
  it("offers a ready update with both versions", () => {
    expect(appUpdateRow(shell({ update: { version: "0.1.1", notes: "Fixes." } })))
      .toEqual({ state: "ready", text: "0.1.0 → 0.1.1", notes: "Fixes." });
  });
  it("shows a refused update as refused, with what stayed in place", () => {
    const refused = shell({ update: { version: "0.1.1", notes: null }, update_error: "signature mismatch" });
    expect(appUpdateRow(refused)).toEqual({ state: "refused", text: "0.1.0 → 0.1.1", notes: null });
    expect(refusedText(refused)).toBe("The update was not installed: signature mismatch. You are still on 0.1.0 and nothing was changed.");
  });
  it("a failed check with no known update is an error line, not a ready update", () => {
    const failed = shell({ update_error: "network is down" });
    expect(appUpdateRow(failed)).toEqual({ state: "check-failed", text: "0.1.0", notes: null });
  });
  it("tray line names the app update and counts the other updates", () => {
    expect(readyLine(shell({ update: { version: "0.1.1", notes: null } }), 2)).toBe("App 0.1.1 is ready · 2 more updates");
    expect(readyLine(shell({ update: { version: "0.1.1", notes: null } }), 1)).toBe("App 0.1.1 is ready · 1 more update");
    expect(readyLine(shell({ update: { version: "0.1.1", notes: null } }), 0)).toBe("App 0.1.1 is ready");
    expect(readyLine(shell({}), 2)).toBeNull();
    expect(readyLine(shell({ update: { version: "0.1.1", notes: null }, update_error: "x" }), 0)).toBeNull();
  });
});

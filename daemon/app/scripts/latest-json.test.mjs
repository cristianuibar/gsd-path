import { describe, expect, it } from "vitest";
import { buildLatest } from "./latest-json.mjs";

const assets = [
  { name: "updater-darwin-aarch64.app.tar.gz.sig", signature: "SIG-A\n" },
  { name: "updater-darwin-x86_64.app.tar.gz.sig", signature: "SIG-B" },
  { name: "updater-windows-x86_64.msi.sig", signature: "SIG-C" },
  { name: "updater-linux-x86_64.AppImage.sig", signature: "SIG-D" },
  { name: "updater-linux-x86_64-deb.deb.sig", signature: "SIG-E" },
];
const input = { tag: "app-v0.1.1", repo: "open-gsd/gsd-path", notes: "Fixes.", pubDate: "2026-10-02T00:00:00Z", assets };

describe("buildLatest", () => {
  it("lists each platform with its signature and the download address of its artifact", () => {
    const latest = buildLatest(input);
    expect(latest.version).toBe("0.1.1");
    expect(latest.notes).toBe("Fixes.");
    expect(latest.pub_date).toBe("2026-10-02T00:00:00Z");
    expect(latest.platforms).toEqual({
      "darwin-aarch64": { signature: "SIG-A", url: "https://github.com/open-gsd/gsd-path/releases/download/app-v0.1.1/updater-darwin-aarch64.app.tar.gz" },
      "darwin-x86_64": { signature: "SIG-B", url: "https://github.com/open-gsd/gsd-path/releases/download/app-v0.1.1/updater-darwin-x86_64.app.tar.gz" },
      "windows-x86_64": { signature: "SIG-C", url: "https://github.com/open-gsd/gsd-path/releases/download/app-v0.1.1/updater-windows-x86_64.msi" },
      "linux-x86_64": { signature: "SIG-D", url: "https://github.com/open-gsd/gsd-path/releases/download/app-v0.1.1/updater-linux-x86_64.AppImage" },
      "linux-x86_64-deb": { signature: "SIG-E", url: "https://github.com/open-gsd/gsd-path/releases/download/app-v0.1.1/updater-linux-x86_64-deb.deb" },
    });
  });
  it("refuses a release with a missing platform, so no app is pointed at an incomplete update", () => {
    expect(() => buildLatest({ ...input, assets: assets.slice(1) })).toThrow("darwin-aarch64");
    // The AppImage signature must not stand in for the .deb.
    expect(() => buildLatest({ ...input, assets: assets.slice(0, 4) })).toThrow("linux-x86_64-deb");
  });
  it("refuses an empty signature and a tag that is not an app version", () => {
    expect(() => buildLatest({ ...input, assets: [{ ...assets[0], signature: " \n" }, ...assets.slice(1)] })).toThrow("signature");
    expect(() => buildLatest({ ...input, tag: "v1.4.0" })).toThrow("app-v");
  });
  it("ignores files that are not updater signatures", () => {
    const latest = buildLatest({ ...input, assets: [...assets, { name: "OpenGSD.Path_0.1.1_aarch64.dmg", signature: "" }] });
    expect(Object.keys(latest.platforms)).toHaveLength(5);
  });
});

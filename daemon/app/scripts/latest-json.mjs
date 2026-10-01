// Builds latest.json, the file the app's updater reads, from the signatures of one release.
// Run by the App release workflow:
//   node scripts/latest-json.mjs <tag> <repo> <dir with updater-*.sig files> > latest.json
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

// The updater asks for "<os>-<arch>"; each build uploads "updater-<os>-<arch>.<ext>" and its ".sig".
export const PLATFORMS = ["darwin-aarch64", "darwin-x86_64", "windows-x86_64", "linux-x86_64"];

export function buildLatest({ tag, repo, notes, pubDate, assets }) {
  if (!/^app-v\d+\.\d+\.\d+/.test(tag)) throw new Error(`the tag must be app-v<version>, not ${tag}`);
  const platforms = {};
  for (const platform of PLATFORMS) {
    const asset = assets.find((item) => item.name.startsWith(`updater-${platform}.`) && item.name.endsWith(".sig"));
    // Every platform or none: an app must never be pointed at an update that has no build for it.
    if (!asset) throw new Error(`no updater signature for ${platform}`);
    const signature = asset.signature.trim();
    if (!signature) throw new Error(`the signature for ${platform} is empty`);
    platforms[platform] = {
      signature,
      url: `https://github.com/${repo}/releases/download/${tag}/${asset.name.slice(0, -".sig".length)}`,
    };
  }
  return { version: tag.slice("app-v".length), notes, pub_date: pubDate, platforms };
}

if (import.meta.url === pathToFileURL(process.argv[1] ?? "").href) {
  const [tag, repo, dir] = process.argv.slice(2);
  const assets = readdirSync(dir).map((name) => ({ name, signature: readFileSync(join(dir, name), "utf8") }));
  const latest = buildLatest({ tag, repo, assets, pubDate: new Date().toISOString(),
    notes: `OpenGSD Path app ${tag.slice("app-v".length)}` });
  process.stdout.write(JSON.stringify(latest, null, 2) + "\n");
}

import { describe, expect, it } from "vitest";
import { building, status } from "./fixtures";
import { addUnique, configChanges, needsPrice, parseWhole, priceRows, toDraft, toPrices, unpricedModels, withUnpriced } from "./settingsConfig";
import type { Config } from "./settingsConfig";

const config: Config = {
  parents: ["/work"], excludes: ["/work/archive"], max_depth: 6, poll_seconds: 5, notify: true, history: true,
  session_dirs: ["~/.codex/sessions"], prices: { "gpt-6-astra": { input: 1.25, cached: 0.125, output: 10 } },
};
const draft = (unpriced: string[] = []) => toDraft(config, unpriced);

describe("unpricedModels", () => {
  it("collects the models without a price from every project, once each, sorted", () => {
    const projects = [
      { ...building, spend: { ...building.spend, unpriced: ["zeta", "claude-sonnet-5"] } },
      { ...building, root: "/b", spend: { unpriced: ["claude-sonnet-5"] } },
      { ...building, root: "/c", spend: null },
    ];
    expect(unpricedModels({ ...status, projects })).toEqual(["claude-sonnet-5", "zeta"]);
  });
  it("is empty before the first status", () => {
    expect(unpricedModels(null)).toEqual([]);
  });
});

describe("parseWhole", () => {
  it("accepts whole numbers of 1 or more", () => {
    expect(parseWhole(" 6 ", "Scan depth")).toEqual({ value: 6 });
    expect(parseWhole("1", "Scan depth")).toEqual({ value: 1 });
  });
  it("refuses zero, fractions, signs and text with the field name", () => {
    for (const text of ["0", "2.5", "-3", "abc", "", "1e2", "6 folders"]) {
      expect(parseWhole(text, "Scan depth")).toEqual({ error: "Scan depth must be a whole number of 1 or more." });
    }
  });
});

describe("priceRows", () => {
  it("lists configured prices by model name, then models that need a price", () => {
    const rows = priceRows({ zed: { input: 2 }, "gpt-6-astra": config.prices["gpt-6-astra"] }, ["claude-sonnet-5", "zed"]);
    expect(rows).toEqual([
      { id: 0, model: "gpt-6-astra", input: "1.25", cached: "0.125", output: "10", known: true, unpriced: false },
      { id: 1, model: "zed", input: "2", cached: "", output: "", known: true, unpriced: true },
      { id: 2, model: "claude-sonnet-5", input: "", cached: "", output: "", known: true, unpriced: true },
    ]);
  });
  it("highlights a model from usage only while its row is empty", () => {
    const [priced, , empty] = priceRows({ zed: { input: 2 }, a: { input: 1 } }, ["zed", "new"]);
    expect(needsPrice(empty)).toBe(true);
    expect(needsPrice({ ...empty, output: "3" })).toBe(false);
    expect(needsPrice(priced)).toBe(false);
    expect(needsPrice({ ...priced, input: "" })).toBe(false); // not seen in usage
  });
});

describe("withUnpriced", () => {
  it("adds a row for a model that usage reports later, and keeps the edits", () => {
    const edited = priceRows({ a: { input: 1 } }, ["b"]).map((row) => ({ ...row, output: "9" }));
    expect(withUnpriced(edited, ["b", "c"])).toEqual([
      { id: 0, model: "a", input: "1", cached: "", output: "9", known: true, unpriced: false },
      { id: 1, model: "b", input: "", cached: "", output: "9", known: true, unpriced: true },
      { id: 2, model: "c", input: "", cached: "", output: "", known: true, unpriced: true },
    ]);
  });
  it("does not repeat a model the user already typed", () => {
    const typed = [{ id: 4, model: "c ", input: "2", cached: "", output: "", known: false, unpriced: false }];
    expect(withUnpriced(typed, ["c"])).toEqual([{ ...typed[0], unpriced: true }]);
  });
});

describe("toPrices", () => {
  const rows = priceRows(config.prices, ["claude-sonnet-5"]);
  it("drops empty rows and keeps only the filled prices", () => {
    expect(toPrices(rows)).toEqual({ prices: config.prices });
    expect(toPrices([{ ...rows[1], cached: " 0.3 " }])).toEqual({ prices: { "claude-sonnet-5": { cached: 0.3 } } });
    expect(toPrices([{ id: 9, model: "  ", input: "", cached: "", output: "", known: false, unpriced: false }])).toEqual({ prices: {} });
  });
  it("accepts zero and refuses negative numbers and text", () => {
    expect(toPrices([{ ...rows[0], input: "0" }])).toMatchObject({ prices: { "gpt-6-astra": { input: 0 } } });
    expect(toPrices([{ ...rows[0], input: "-1", output: "ten" }])).toEqual({ errors: [
      "The input price for gpt-6-astra must be a number of 0 or more.",
      "The output price for gpt-6-astra must be a number of 0 or more.",
    ] });
  });
  it("refuses a price without a model name and a model listed twice", () => {
    expect(toPrices([{ id: 9, model: "", input: "1", cached: "", output: "", known: false, unpriced: false }]))
      .toEqual({ errors: ["Type a model name for the new price row."] });
    expect(toPrices([rows[0], { ...rows[0], id: 9, known: false }])).toEqual({ errors: ["gpt-6-astra is listed twice."] });
  });
});

describe("configChanges", () => {
  it("sends nothing when nothing changed", () => {
    expect(configChanges(config, draft(["claude-sonnet-5"]))).toEqual({ payload: {}, errors: [], summary: [] });
  });
  it("sends only the keys that changed", () => {
    const next = { ...draft(), max_depth: "4", notify: false };
    expect(configChanges(config, next)).toEqual({
      payload: { max_depth: 4, notify: false }, errors: [],
      summary: ["Scan depth: 6 → 4", "Desktop notifications: on → off"],
    });
  });
  it("sends a whole list when a folder is added or removed", () => {
    const next = { ...draft(), parents: ["/work", "/src"], excludes: [], session_dirs: ["~/.claude/projects/*"] };
    expect(configChanges(config, next)).toEqual({
      payload: { parents: ["/work", "/src"], excludes: [], session_dirs: ["~/.claude/projects/*"] }, errors: [],
      summary: ["Watch /src", "Stop excluding /work/archive", "Add session folder ~/.claude/projects/*", "Remove session folder ~/.codex/sessions"],
    });
  });
  it("sends all prices when one changed, and names the models", () => {
    const base = draft(["claude-sonnet-5"]);
    const next = { ...base, prices: base.prices.slice(1).map((row) => ({ ...row, input: "3", output: "15" })) };
    expect(configChanges(config, next)).toEqual({
      payload: { prices: { "claude-sonnet-5": { input: 3, output: 15 } } }, errors: [],
      summary: ["Remove the price for gpt-6-astra", "Set the price for claude-sonnet-5"],
    });
    const edited = { ...base, prices: base.prices.map((row) => (row.model === "gpt-6-astra" ? { ...row, output: "12" } : row)) };
    expect(configChanges(config, edited).summary).toEqual(["Change the price for gpt-6-astra"]);
  });
  it("reports bad values and sends nothing", () => {
    const base = draft();
    const next = { ...base, max_depth: "0", poll_seconds: "x", history: false, prices: [{ ...base.prices[0], cached: "-2" }] };
    const result = configChanges(config, next);
    expect(result.payload).toEqual({});
    expect(result.errors).toEqual([
      "Scan depth must be a whole number of 1 or more.",
      "Refresh interval must be a whole number of 1 or more.",
      "The cached price for gpt-6-astra must be a number of 0 or more.",
    ]);
  });
});

describe("addUnique", () => {
  it("adds a trimmed item once and ignores an empty one", () => {
    expect(addUnique(["/a"], " /b ")).toEqual(["/a", "/b"]);
    expect(addUnique(["/a"], "/a")).toEqual(["/a"]);
    expect(addUnique(["/a"], "  ")).toEqual(["/a"]);
    expect(addUnique(["/a"], null)).toEqual(["/a"]);
  });
});

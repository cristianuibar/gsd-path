import { describe, expect, it } from "vitest";
import { buildChanges, diffLines, fileNote, gitPill, hide, isDirty, jevOn, jevPlan, MASK, needsValue, newRow, refusal, rowErrors, rowsFrom, valueView } from "./env";
import type { EnvRow } from "./env";

const listed = [{ name: "API_KEY", empty: false }, { name: "LOG_LEVEL", empty: false }, { name: "EMPTY", empty: true }];
const rows = () => rowsFrom(listed);
const edit = (list: EnvRow[], at: number, over: Partial<EnvRow>) => list.map((row, index) => (index === at ? { ...row, ...over } : row));

describe("rows", () => {
  it("starts every listed variable hidden, with no value in memory", () => {
    expect(rows()).toEqual([
      { key: 0, original: "API_KEY", name: "API_KEY", empty: false, draft: null, disk: null, shown: false, removed: false },
      { key: 1, original: "LOG_LEVEL", name: "LOG_LEVEL", empty: false, draft: null, disk: null, shown: false, removed: false },
      { key: 2, original: "EMPTY", name: "EMPTY", empty: true, draft: null, disk: null, shown: false, removed: false },
    ]);
  });
  it("adds an editable row with a key no other row has", () => {
    expect(newRow(rows())).toEqual({ key: 3, original: null, name: "", empty: true, draft: null, disk: null, shown: true, removed: false });
    expect(newRow([]).key).toBe(0);
  });
});

describe("valueView", () => {
  it("masks a value with 12 bullets until the user chooses Show", () => {
    expect(MASK).toBe("••••••••••••");
    expect(valueView(rows()[0])).toBeNull(); // null: draw the mask
    expect(valueView({ ...rows()[0], shown: true, disk: "s3cret" })).toBe("s3cret");
  });
  it("stays masked while the value is not loaded, also after Show", () => {
    expect(valueView({ ...rows()[0], shown: true })).toBeNull();
  });
  it("shows an empty value as empty, not as bullets", () => {
    expect(valueView(rows()[2])).toBe("");
    expect(valueView({ ...rows()[0], draft: "" })).toBe("");
  });
  it("shows the edit, not the value on disk", () => {
    expect(valueView({ ...rows()[0], shown: true, disk: "old", draft: "new" })).toBe("new");
  });
  it("masks an edited value again after Hide and forgets the value read from the file", () => {
    const hidden = hide({ ...rows()[0], shown: true, disk: "old", draft: "new" });
    expect(hidden).toMatchObject({ shown: false, disk: null, draft: "new" });
    expect(valueView(hidden)).toBeNull();
    expect(hide({ ...rows()[1], shown: true, disk: "info" })).toEqual(rows()[1]);
  });
});

describe("rowErrors", () => {
  const error = (name: string) => rowErrors(edit(rows(), 1, { name }))[1];
  it("accepts letters, digits and _, not starting with a digit", () => {
    expect(rowErrors(rows())).toEqual({});
    expect(error("_a1")).toBeUndefined();
    expect(error("lower_Case9")).toBeUndefined();
  });
  it("refuses an empty name, a leading digit, and other characters", () => {
    const rule = "A name has letters, digits, and _ only, and does not start with a digit.";
    expect(error("")).toBe("Enter a name.");
    expect(error("1ABC")).toBe(rule);
    expect(error("MY-KEY")).toBe(rule);
    expect(error("A B")).toBe(rule);
    expect(error("A=B")).toBe(rule);
    expect(error("KEY\n")).toBe(rule);
  });
  it("refuses a name that two rows use", () => {
    const list = [...rows(), { ...newRow(rows()), name: "API_KEY" }];
    expect(rowErrors(list)).toEqual({ 0: "This name is used more than once.", 3: "This name is used more than once." });
  });
  it("refuses a new row that takes the name of a removed or renamed variable", () => {
    const added = { ...newRow(rows()), name: "API_KEY" };
    expect(rowErrors([...edit(rows(), 0, { removed: true }), added])).toEqual({ 3: "This name is used more than once." });
    expect(rowErrors([...edit(rows(), 0, { name: "TOKEN" }), added])).toEqual({ 3: "This name is used more than once." });
  });
  it("does not check a removed row", () => {
    expect(rowErrors(edit(rows(), 1, { name: "1bad", removed: true }))).toEqual({});
  });
});

describe("buildChanges", () => {
  it("produces nothing for unchanged rows, also after Show", () => {
    expect(buildChanges(rows(), {})).toEqual([]);
    expect(buildChanges(edit(rows(), 0, { shown: true, disk: "s3cret" }), {})).toEqual([]);
    expect(isDirty(rows())).toBe(false);
  });
  it("produces nothing when an edit equals the value in the file", () => {
    expect(buildChanges(edit(rows(), 0, { disk: "same", draft: "same" }), {})).toEqual([]);
    expect(buildChanges(edit(rows(), 2, { draft: "" }), {})).toEqual([]);
    expect(isDirty(edit(rows(), 2, { draft: "" }))).toBe(false);
  });
  it("sends a changed value", () => {
    const list = edit(rows(), 1, { disk: "info", draft: "debug" });
    expect(buildChanges(list, {})).toEqual([{ name: "LOG_LEVEL", value: "debug" }]);
    expect(buildChanges(edit(rows(), 0, { draft: "" }), {})).toEqual([{ name: "API_KEY", value: "" }]);
    expect(isDirty(list)).toBe(true);
  });
  it("sends a removal by the name in the file", () => {
    const list = edit(rows(), 0, { removed: true, name: "RENAMED", draft: "x" });
    expect(buildChanges(list, {})).toEqual([{ name: "API_KEY", remove: true }]);
    expect(isDirty(list)).toBe(true);
  });
  it("sends an added row; no value typed is an empty value", () => {
    const added = { ...newRow(rows()), name: "NEW_VARIABLE" };
    expect(buildChanges([...rows(), added], {})).toEqual([{ name: "NEW_VARIABLE", value: "" }]);
    expect(buildChanges([...rows(), { ...added, draft: "v" }], {})).toEqual([{ name: "NEW_VARIABLE", value: "v" }]);
    expect(isDirty([...rows(), added])).toBe(true);
  });
  it("turns a rename into remove + add, with the edited value", () => {
    const list = edit(rows(), 1, { name: "LOG", draft: "warn" });
    expect(needsValue(list)).toEqual([]);
    expect(buildChanges(list, {})).toEqual([{ name: "LOG_LEVEL", remove: true }, { name: "LOG", value: "warn" }]);
  });
  it("needs the file's value for a rename without an edit, and uses it", () => {
    const list = edit(rows(), 0, { name: "TOKEN" });
    expect(needsValue(list)).toEqual(["API_KEY"]);
    expect(buildChanges(list, { API_KEY: "s3cret" })).toEqual([{ name: "API_KEY", remove: true }, { name: "TOKEN", value: "s3cret" }]);
    expect(() => buildChanges(list, {})).toThrow("The value of API_KEY is not loaded.");
    expect(isDirty(list)).toBe(true);
  });
  it("needs no read for a renamed empty variable", () => {
    const list = edit(rows(), 2, { name: "BLANK" });
    expect(needsValue(list)).toEqual([]);
    expect(buildChanges(list, {})).toEqual([{ name: "EMPTY", remove: true }, { name: "BLANK", value: "" }]);
  });
});

describe("Jev screening", () => {
  it("is on in the files where the flag is 1", () => {
    expect(jevOn({})).toEqual([]);
    expect(jevOn({ ".env": "0", ".env.local": "1", ".env.production": "" })).toEqual([".env.local"]);
  });
  it("on: writes the flag to the chosen file only", () => {
    expect(jevPlan(true, ".env.local", {})).toEqual([{ file: ".env.local", changes: [{ name: "GSD_PATH_JEV", value: "1" }] }]);
    expect(jevPlan(true, ".env", { ".env": "0" })).toEqual([{ file: ".env", changes: [{ name: "GSD_PATH_JEV", value: "1" }] }]);
  });
  it("off: removes the flag from every file where it is on, and touches no other file", () => {
    expect(jevPlan(false, ".env.local", { ".env": "1", ".env.local": "0", ".env.production": "1" })).toEqual([
      { file: ".env", changes: [{ name: "GSD_PATH_JEV", remove: true }] },
      { file: ".env.production", changes: [{ name: "GSD_PATH_JEV", remove: true }] },
    ]);
    expect(jevPlan(false, ".env.local", {})).toEqual([]);
  });
});

describe("file facts", () => {
  it("warns for a tracked file, is calm for an ignored one", () => {
    expect(gitPill("tracked")).toEqual({ tone: "warn", label: "Tracked by Git" });
    expect(gitPill("ignored")).toEqual({ tone: "ok", label: "Ignored by Git" });
    expect(gitPill("untracked")).toEqual({ tone: "mute", label: "Not tracked" });
  });
  it("says what Git does with the values, and when the file is not there yet", () => {
    const file = (git: "tracked" | "ignored" | "untracked", exists = true) => fileNote({ file: ".env", exists, git, vars: [] });
    expect(file("tracked")).toBe("Values in .env would be committed. Keep secrets in .env.local.");
    expect(file("ignored")).toBe(".env is listed in .gitignore, so these values stay out of commits.");
    expect(file("untracked")).toBe(".env is not in Git and not in .gitignore, so a commit can still pick it up. Keep secrets in .env.local.");
    expect(file("ignored", false)).toBe(".env is listed in .gitignore, so these values stay out of commits. The file does not exist yet; Save creates it.");
  });
  it("names each change of a save preview without a value", () => {
    expect(diffLines([{ name: "A", change: "add" }, { name: "B", change: "change" }, { name: "C", change: "remove" }]))
      .toEqual(["Add A", "Change B", "Remove C"]);
  });
});

describe("refusal", () => {
  it("is the reason when the monitor refuses every file with the same message", () => {
    expect(refusal(["No write token.", "No write token.", "No write token.", "No write token."])).toBe("No write token.");
  });
  it("is not a refusal when a file loads or the messages differ", () => {
    expect(refusal([null, ".env.production is a link or not a regular file; it is not opened", null, null])).toBeNull();
    expect(refusal(["a", "b", "a", "a"])).toBeNull();
    expect(refusal([])).toBeNull();
  });
});

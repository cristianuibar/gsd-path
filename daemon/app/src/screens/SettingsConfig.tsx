// Settings → Monitoring and Usage and prices: two views of one form over /api/config.
import { useEffect, useState } from "react";
import { addUnique, configChanges, needsPrice, PRICE_KEYS, toDraft, unpricedModels, withUnpriced } from "../settingsConfig";
import type { Config, Draft, PriceRow } from "../settingsConfig";
import { api, pickFolder } from "../shell";
import type { Status } from "../status";
import { Field, SaveBar, Toggle } from "./SettingsParts";

/** The form lives in the Settings page, so an edit survives a change of tab. */
export function useConfigForm(status: Status | null) {
  const unpriced = unpricedModels(status);
  const [config, setConfig] = useState<Config | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [note, setNote] = useState("");

  useEffect(() => {
    api<Config>("GET", "/api/config").then(setConfig, (reason) => setError(String(reason)));
  }, []);
  // A new saved config replaces the draft. A model that usage reports later only adds its empty row.
  useEffect(() => { if (config) setDraft(toDraft(config, unpriced)); }, [config]);
  const models = unpriced.join("\n");
  useEffect(() => {
    setDraft((old) => old && { ...old, prices: withUnpriced(old.prices, unpriced) });
  }, [models]);

  const changes = config && draft ? configChanges(config, draft) : { payload: {}, errors: [], summary: [] };
  const set = (part: Partial<Draft>) => { setNote(""); setDraft((old) => old && { ...old, ...part }); };
  const save = async () => {
    setBusy(true); setError(""); setNote("");
    try {
      setConfig(await api<Config>("POST", "/api/config", changes.payload));
      setNote("Saved.");
    } catch (reason) {
      setError(String(reason)); // the daemon refused: nothing changed
    }
    setBusy(false);
  };
  const discard = () => { setError(""); if (config) setDraft(toDraft(config, unpriced)); };
  const bar = <SaveBar summary={changes.summary} errors={changes.errors} error={error} note={note} busy={busy} onSave={save} onDiscard={discard} />;
  return { draft, set, busy, error, bar };
}
type Form = ReturnType<typeof useConfigForm>;

function Loading({ title, error }: { title: string; error: string }) {
  return (
    <>
      <h2 className="set-h2">{title}</h2>
      {error ? <div className="error" role="alert">Cannot read the settings. {error}</div> : <p className="note">Loading settings…</p>}
    </>
  );
}

/** A folder list with a remove button per line and a folder dialog to add one. */
function Folders({ name, items, empty, remove, add, danger, disabled, onChange }: {
  name: string; items: string[]; empty: string; remove: string; add: string; danger?: boolean; disabled: boolean; onChange: (items: string[]) => void;
}) {
  const [error, setError] = useState("");
  const pick = () => pickFolder().then((folder) => { setError(""); onChange(addUnique(items, folder)); }, (reason) => setError(String(reason)));
  return (
    <div className="set-block">
      <b>{name}</b>
      {items.map((item) => (
        <div key={item} className="set-item">
          <span>{item}</span>
          <button className={danger ? "btn small danger" : "btn small"} disabled={disabled} onClick={() => onChange(items.filter((other) => other !== item))}>{remove}</button>
        </div>
      ))}
      {!items.length && <div className="sub">{empty}</div>}
      <button className="btn small set-add" disabled={disabled} onClick={pick}>{add}</button>
      {error && <div className="error" role="alert">{error}</div>}
    </div>
  );
}

export function MonitoringTab({ form }: { form: Form }) {
  const { draft, set, busy } = form;
  if (!draft) return <Loading title="Monitoring" error={form.error} />;
  const number = (key: "max_depth" | "poll_seconds", label: string) => (
    <input className="set-input num" inputMode="numeric" aria-label={label} value={draft[key]} disabled={busy}
      onChange={(event) => set({ [key]: event.target.value })} />
  );
  return (
    <>
      <h2 className="set-h2">Monitoring</h2>
      <div className="card set-card">
        <Folders name="Watched folders" items={draft.parents} remove="Stop watching" add="Add folder…" danger disabled={busy}
          empty="No watched folders. Projects are found only inside a watched folder." onChange={(parents) => set({ parents })} />
        <Folders name="Excluded folders" items={draft.excludes} remove="Remove" add="Exclude folder…" disabled={busy}
          empty="No excluded folders." onChange={(excludes) => set({ excludes })} />
        <Field name="Scan depth" hint="How many folders deep to look for projects.">{number("max_depth", "Scan depth")}</Field>
        <Field name="Refresh interval" hint="Seconds between reads of project state.">{number("poll_seconds", "Refresh interval")}</Field>
        <Field name="Desktop notifications" hint="Phase changes, blocks and pending answers.">
          <Toggle on={draft.notify} label="Desktop notifications" disabled={busy} onChange={(notify) => set({ notify })} />
        </Field>
        <Field name="Activity history" hint={<>Keep a record of changes in <span className="mono">history.jsonl</span>.</>}>
          <Toggle on={draft.history} label="Activity history" disabled={busy} onChange={(history) => set({ history })} />
        </Field>
      </div>
      {form.bar}
    </>
  );
}

export function UsageTab({ form }: { form: Form }) {
  const { draft, set, busy } = form;
  const [pattern, setPattern] = useState("");
  if (!draft) return <Loading title="Usage and prices" error={form.error} />;
  const rows = draft.prices;
  const change = (id: number, part: Partial<PriceRow>) => set({ prices: rows.map((row) => (row.id === id ? { ...row, ...part } : row)) });
  // A model that usage reports keeps its row: Remove only empties it.
  const remove = (row: PriceRow) => (row.unpriced ? change(row.id, { input: "", cached: "", output: "" })
    : set({ prices: rows.filter((other) => other.id !== row.id) }));
  const addModel = () => set({ prices: [...rows, { id: Math.max(-1, ...rows.map((row) => row.id)) + 1, model: "",
    input: "", cached: "", output: "", known: false, unpriced: false }] });
  const addPattern = () => { set({ session_dirs: addUnique(draft.session_dirs, pattern) }); setPattern(""); };
  const missing = rows.filter(needsPrice);

  return (
    <>
      <h2 className="set-h2 tight">Usage and prices</h2>
      <p className="set-lead">Cost is tokens times the price per million tokens. A model without a price shows tokens only.</p>
      <div className="card set-pad">
        <div className="set-prices">
          <span className="set-th">Model</span><span className="set-th num">Input</span><span className="set-th num">Cached</span>
          <span className="set-th num">Output</span><span />
          {rows.map((row) => (
            <div key={row.id} className={needsPrice(row) ? "set-price missing" : "set-price"}>
              {row.known ? <span className="mono">{row.model}</span>
                : <input className="set-input mono" aria-label="Model name" placeholder="model name" value={row.model} disabled={busy}
                    onChange={(event) => change(row.id, { model: event.target.value })} />}
              {PRICE_KEYS.map((key) => (
                <input key={key} className="set-input num" inputMode="decimal" placeholder="—" disabled={busy}
                  aria-label={`${key} price for ${row.model || "the new model"}`} value={row[key]}
                  onChange={(event) => change(row.id, { [key]: event.target.value })} />
              ))}
              <button className="link" disabled={busy || needsPrice(row)} onClick={() => remove(row)}>Remove</button>
            </div>
          ))}
        </div>
        {!rows.length && <div className="sub">No prices yet. Cost stays blank until a model has a price.</div>}
        {missing.map((row) => <div key={row.id} className="set-missing">{row.model} has no price. Its cost is left out of totals.</div>)}
        <button className="btn small set-add" disabled={busy} onClick={addModel}>Add a model</button>
      </div>
      <div className="card set-pad set-gap">
        <b>Session folders</b>
        <div className="sub">Where agent session logs are read for tokens. A folder can be a glob pattern.</div>
        {draft.session_dirs.map((item) => (
          <div key={item} className="set-item">
            <span>{item}</span>
            <button className="btn small" disabled={busy} onClick={() => set({ session_dirs: draft.session_dirs.filter((other) => other !== item) })}>Remove</button>
          </div>
        ))}
        {!draft.session_dirs.length && <div className="sub set-warn">No session folders. Usage cannot be read.</div>}
        <form className="set-new" onSubmit={(event) => { event.preventDefault(); addPattern(); }}>
          <input className="set-input mono" aria-label="Session folder or pattern" placeholder="~/.codex/sessions" value={pattern}
            disabled={busy} onChange={(event) => setPattern(event.target.value)} />
          <button className="btn small" disabled={busy || !pattern.trim()}>Add folder</button>
        </form>
      </div>
      {form.bar}
    </>
  );
}

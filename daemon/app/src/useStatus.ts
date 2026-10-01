import { useEffect, useState } from "react";
import { api } from "./shell";
import { pollMs } from "./status";
import type { Status } from "./status";

/** Polls /status. When the monitor does not answer, the last payload stays and `offline` is true. */
export function useStatus(restart: unknown) {
  const [status, setStatus] = useState<Status | null>(null);
  const [offline, setOffline] = useState(false);
  const [round, setRound] = useState(0);

  useEffect(() => {
    let live = true;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      const next = await api<Status>("GET", "/status").catch(() => null);
      if (!live) return;
      if (next) setStatus(next);
      setOffline(!next);
      timer = setTimeout(poll, pollMs(next));
    };
    poll();
    return () => { live = false; clearTimeout(timer); };
  }, [restart, round]);

  /** Ask the monitor for a new scan, then read the result. */
  const refresh = async () => {
    await api("POST", "/api/refresh").catch(() => null); // an offline monitor shows as offline on the next poll
    setRound((count) => count + 1);
  };
  return { status, offline, refresh };
}

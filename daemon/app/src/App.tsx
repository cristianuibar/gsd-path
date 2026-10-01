import { useEffect, useState } from "react";
import { pickScreen } from "./screen";
import { boot, getShell, onShellChange, usePort } from "./shell";
import type { Shell } from "./shell";
import { FirstLaunch } from "./screens/FirstLaunch";
import { BlockingProblems, PortInUse, PythonMissing } from "./screens/Problems";
import { Ready } from "./screens/Ready";
import { Requirements } from "./screens/Requirements";

const SETUP_DONE = "gsd-path.setup-done";

export function App() {
  const [shell, setShell] = useState<Shell | null>(null);
  const [setupDone, setSetupDone] = useState(() => localStorage.getItem(SETUP_DONE) === "1");
  const [firstLaunchSeen, setFirstLaunchSeen] = useState(false);

  useEffect(() => {
    getShell().then(setShell);
    // The tray can also start, stop, or restart the monitor.
    const stop = onShellChange(setShell);
    return () => { stop.then((off) => off()); };
  }, []);

  if (!shell) return null;
  const retry = () => { setShell({ ...shell, phase: "checking" }); boot().then(setShell); };
  const finishSetup = () => { localStorage.setItem(SETUP_DONE, "1"); setSetupDone(true); };

  switch (pickScreen(shell, { setupDone, firstLaunchSeen })) {
    case "checking":
      return <div className="center"><p className="lead">Checking your setup…</p></div>;
    case "first-launch":
      return <FirstLaunch shell={shell} onRetry={retry} onDone={() => setFirstLaunchSeen(true)} />;
    case "requirements":
      return <Requirements shell={shell} onRetry={retry} onDone={finishSetup} />;
    case "python":
      return <PythonMissing shell={shell} onRetry={retry} />;
    case "port":
      return <PortInUse shell={shell} onRetry={retry}
        problem={shell.launch!.problems.find((problem) => problem.kind === "port")!}
        onUsePort={(port) => { setShell({ ...shell, phase: "checking" }); usePort(port).then(setShell); }} />;
    case "problem":
      return <BlockingProblems shell={shell} onRetry={retry} />;
    case "ready":
      return <Ready shell={shell} onStart={retry} />;
  }
}

// States where no monitor runs: Python missing, port taken, or another blocking problem.
import { heldByDaemon, programName, pythonFix } from "../screen";
import type { Problem, Shell } from "../shell";
import { ActionButton, CopyButton, FixText, firstCommand } from "../ui";

function Page({ children }: { children: React.ReactNode }) {
  return <div className="center"><div className="column">{children}</div></div>;
}

export function PythonMissing({ shell, onRetry }: { shell: Shell; onRetry: () => void }) {
  const fix = pythonFix(shell.os);
  return (
    <Page>
      <div className="problem">
        <b>Python 3.9 or newer is needed</b>
        <span>OpenGSD Path runs its background monitor on Python. Nothing has been started or changed.</span>
        {"copy" in fix && <div className="code">{fix.copy}</div>}
        <div className="actions">
          <button className="btn primary" onClick={onRetry}>Check again</button>
          <ActionButton action={fix} primary={false} />
        </div>
      </div>
    </Page>
  );
}

export function PortInUse({ shell, problem, onRetry, onUsePort }: {
  shell: Shell; problem: Problem; onRetry: () => void; onUsePort: (port: number) => void;
}) {
  const { pid } = problem.detail ?? {};
  // The daemon reports the whole command line; the program name is enough here.
  const command = programName(problem.detail?.command);
  if (heldByDaemon(problem)) {
    return (
      <Page>
        <div className="problem">
          <b>Port {shell.port} is already in use</b>
          <span>{problem.message} <FixText text={problem.fix} /></span>
          <div className="actions">
            <button className="btn primary" onClick={onRetry}>Check again</button>
            <button className="btn" onClick={() => onUsePort(shell.port + 1)}>Use port {shell.port + 1}</button>
          </div>
        </div>
      </Page>
    );
  }
  return (
    <Page>
      <div className="problem">
        <b>Port {shell.port} is already in use</b>
        <span>
          {command
            ? <>A program named <span className="mono">{command}</span>{pid ? ` (pid ${pid})` : ""} is listening there. </>
            : "Another program is listening there. "}
          It is not a GSD Path monitor, so the app leaves it running.
        </span>
        <div className="actions">
          <button className="btn primary" onClick={() => onUsePort(shell.port + 1)}>Use port {shell.port + 1}</button>
          <button className="btn" onClick={onRetry}>Check again</button>
        </div>
      </div>
    </Page>
  );
}

export function BlockingProblems({ shell, onRetry }: { shell: Shell; onRetry: () => void }) {
  const problems: Problem[] = shell.launch?.problems.filter((problem) => problem.blocking) ?? [];
  if (!problems.length) {
    problems.push({ kind: "launch", message: "The setup check failed.", fix: shell.error ?? "Choose Check again.", blocking: true });
  }
  return (
    <Page>
      {problems.map((problem) => {
        const command = firstCommand(problem.fix);
        return (
          <div className="problem" key={problem.kind + problem.message}>
            <b>{problem.message}</b>
            <span><FixText text={problem.fix} /> No monitor was started.</span>
            <div className="actions">
              <button className="btn primary" onClick={onRetry}>Check again</button>
              {command && <CopyButton text={command} label="Copy command" />}
            </div>
          </div>
        );
      })}
    </Page>
  );
}

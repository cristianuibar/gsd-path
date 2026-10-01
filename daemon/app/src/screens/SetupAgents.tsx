// Setup, step 2: the agents that get Path skills.
import { agentCards } from "../setup";
import type { HostInfo } from "../skills";

export function SetupAgents({ hosts, selected, onToggle }: { hosts: HostInfo[]; selected: string[]; onToggle: (id: string) => void }) {
  const cards = agentCards(hosts, selected);
  return <>
    <h1 className="title">Your coding agents</h1>
    <p className="lead setup-lead">
      Found {cards.filter((card) => card.found).length} of {cards.length} supported agents. Path skills go into each agent you select.
      Path does not install the agents themselves.
    </p>
    <div className="sk-agents">
      {cards.map((card) => (
        <label key={card.id} className={`sk-agent${card.on ? " on" : ""}${card.found ? "" : " missing"}`}>
          <input type="checkbox" checked={card.on} onChange={() => onToggle(card.id)} />
          <span><b>{card.name}</b><small>{card.note}</small></span>
        </label>
      ))}
    </div>
    <p className="note">Agents that are not found can still be selected.</p>
  </>;
}

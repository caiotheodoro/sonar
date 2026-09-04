/**
 * Third-party numbers, read from external-facts.json through a named
 * accessor. Same discipline as results.ts: an unknown id throws at module
 * evaluation, so a chip cannot silently render nothing.
 */
import raw from "./external-facts.json";

export interface ExternalFact {
  id: string;
  value: number;
  display?: string;
  unit: string;
  label: string;
  source_url: string;
  captured_at: string;
  shot: string;
}

const FACTS: Record<string, ExternalFact> = Object.fromEntries(
  (raw as { facts: ExternalFact[] }).facts.map((f) => [f.id, f]),
);

export const fact = (id: string): ExternalFact => {
  const f = FACTS[id];
  if (!f) throw new Error(`src/data/external-facts.json: no fact "${id}"`);
  return f;
};

export const factText = (id: string): string => {
  const f = fact(id);
  return f.display ?? String(f.value);
};

export const factHost = (id: string): string => new URL(fact(id).source_url).host;

/**
 * The call itself, typed out: the request sonar makes, the run id that comes
 * back, and what that run billed. Every field is read from one real row of
 * the receipt's run ledger, the dearest one, so the id on screen is an id you
 * can look up.
 */
import React from "react";
import { SfxAt } from "../components/Sfx";
import { usd } from "../data/results";
import { RESULTS } from "../manifest";
import { T } from "../theme";
import { Card, useSince, type CardProps } from "./Card";

const RUN = [...RESULTS.receipt.runs].sort((a, b) => (b.costUsd ?? 0) - (a.costUsd ?? 0))[0];

const LINES: { text: string; colour: string }[] = [
  { text: `$ POST /v1/run`, colour: T.plate },
  { text: `    { "provider": "${RUN.provider}", "endpoint": "${RUN.endpoint}" }`, colour: T.engrave },
  { text: `  202  runId ${RUN.runId ?? ""}`, colour: T.plate },
  { text: `$ GET /v1/runs/${RUN.runId ?? ""}`, colour: T.plate },
  { text: `  ${RUN.status}   ${RUN.nResults ?? 0} results   billed ${usd(RUN.costUsd ?? 0)}`, colour: T.signal },
];
const CPF = 3.2;
const LINE_H = 62;
const total = LINES.reduce((a, l) => a + l.text.length, 0);

export const RunRequest: React.FC<CardProps> = () => {
  const f = useSince(0);
  const typed = Math.floor(f * CPF);
  let consumed = 0;
  return (
    <Card plate={["MONID", "POST /v1/run"]} source={["results/demo/receipt.json", `runs[local_seq=${RUN.localSeq}]`, "cost_source /v1/runs"]}>
      <SfxAt src="key" frames={Array.from({ length: Math.ceil(total / 8) }, (_, i) => Math.round((i * 8) / CPF))} gain={0.4} />
      <div style={{ fontFamily: T.mono, fontSize: 38, lineHeight: `${LINE_H}px` }}>
        {LINES.map((l) => {
          const start = consumed;
          consumed += l.text.length;
          const shown = l.text.slice(0, Math.max(0, Math.min(l.text.length, typed - start)));
          return (
            <div key={l.text} style={{ color: l.colour, whiteSpace: "pre" }}>
              {shown}
              {typed > start && typed < consumed ? <span style={{ color: T.signal }}>▌</span> : null}
            </div>
          );
        })}
      </div>
    </Card>
  );
};

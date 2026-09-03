/**
 * Beat 5: the sparse-coverage run. A brand with barely any mentions still
 * produces a receipt that lists every run and its cost, and a digest whose
 * every estimate abstains (no conclusions drawn). The final scene replays
 * public/casts/avenza_empty.cast; its numbers come from that recording and
 * the receipt under results/demo-empty, which the narration task binds. This
 * placeholder shows the demo run's own abstention record so the contrast is
 * visible: what the full run could not check either.
 */
import React from "react";
import { BeatPlaceholder } from "../components/BeatPlaceholder";
import { Checklist } from "../components/Panels";
import { Source } from "../components/DataPanel";
import { RESULTS } from "../manifest";

const { whatCouldNotBeChecked } = RESULTS.receipt;
const { coverageGaps } = RESULTS.digest;

const items = [
  ...whatCouldNotBeChecked,
  ...coverageGaps.map((g) => `${g.source}: ${g.reason}`),
];

export const SceneEmptyRun: React.FC = () => (
  <BeatPlaceholder id="empty-run">
    <Checklist items={items.length ? items : ["every planned source ran"]} />
    <Source file="results/demo/receipt.json · results/demo/digest.json" detail="what_could_not_be_checked · coverage_gaps" />
  </BeatPlaceholder>
);

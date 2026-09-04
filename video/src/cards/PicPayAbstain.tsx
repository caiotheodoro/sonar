/** When data is thin, the same gesture resolves to a dash. Never red; an abstention is not an error. */
import React from "react";
import { ReadLine } from "../components/ReadLine";
import { pct } from "../data/results";
import { RESULTS } from "../manifest";
import { Card, type CardProps } from "./Card";

const abstained = RESULTS.stats.shareOfVoice.find((r) => r.share === null);
if (!abstained) throw new Error("results/demo/stats.json: expected one brand with share null");

export const PicPayAbstain: React.FC<CardProps> = () => (
  <Card plate={["HONEST", "ABSTAIN"]} title="Not enough data, so it says so." source={["results/demo/stats.json", `share_of_voice[brand=${abstained.brand}]`, "share null"]}>
    <ReadLine label={`${abstained.brand}, share of voice`} value={null} domain={[0, 0.5]} format={pct} startFrame={4} width={1100} abstainNote="abstained, on the receipt" />
  </Card>
);

/** The one number this pipeline can be wrong about — its own label audit — read against the bar the repo set. */
import React from "react";
import { ReadLine } from "../components/ReadLine";
import { RESULTS } from "../manifest";
import repoFacts from "../data/repo-facts.json";
import { Card, type CardProps } from "./Card";

const { audit } = RESULTS.receipt;
const twoDp = (n: number): string => n.toFixed(2);

export const Audit: React.FC<CardProps> = () => (
  <Card plate={["HONEST", "LABEL AUDIT"]} title="Printed on the receipt." source={["results/demo/receipt.json", `audit ${audit.nAgree} of ${audit.nSample}`, "src/sonar/config.py H3_MIN_AGREEMENT"]}>
    <ReadLine label="our own label audit, agreement" value={audit.agreement} domain={[0, 1]} format={twoDp} startFrame={2} width={1100} mark={{ value: repoFacts.auditBar, label: `bar ${twoDp(repoFacts.auditBar)}` }} />
  </Card>
);

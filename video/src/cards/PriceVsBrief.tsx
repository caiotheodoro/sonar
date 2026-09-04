/** The seat price and the measured brief on one axis. The old opening, kept as the cost beat. */
import React from "react";
import { ReadLine } from "../components/ReadLine";
import { usd, usdWhole } from "../data/results";
import { RESULTS } from "../manifest";
import { Card, type CardProps } from "./Card";

const { incumbent, totals } = RESULTS.receipt;
const DOMAIN: [number, number] = [0, incumbent.priceUsdMonth];

export const PriceVsBrief: React.FC<CardProps> = () => (
  <Card plate={["COST", "ONE SEAT", "ONE BRIEF"]} source={["results/demo/receipt.json", "incumbent.price_usd_month", "totals.total_usd"]}>
    <div style={{ display: "flex", flexDirection: "column", gap: 60 }}>
      <ReadLine label={`${incumbent.name}, per month`} value={incumbent.priceUsdMonth} domain={DOMAIN} format={usdWhole} startFrame={1} width={1600} />
      <ReadLine label="this brief, measured" value={totals.totalUsd} domain={DOMAIN} format={usd} startFrame={8} width={1600} emphasis />
    </div>
  </Card>
);

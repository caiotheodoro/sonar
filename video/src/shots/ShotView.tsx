/**
 * One shot, drawn. Runs inside a `<Sequence>` so `useCurrentFrame()` is
 * shot-local. Switches on the storyboard's `kind`; every branch reads its
 * figures from RESULTS or `fact()`, never from the storyboard text.
 */
import React from "react";
import { Screenshot } from "../components/Screenshot";
import { Stamp } from "../components/Stamp";
import { ReceiptRows } from "../components/ReceiptRows";
import { CARDS, type CardId } from "../cards";
import { CastShot } from "./CastShot";
import type { ResolvedShot } from "../timeline/types";

export const ShotView: React.FC<{ shot: ResolvedShot }> = ({ shot }) => {
  const s = shot.shot;
  switch (s.kind) {
    case "shot":
      return <Screenshot shot={s} durationInFrames={shot.durationInFrames} />;
    case "stamp":
      return <Stamp variant={s.variant} text={s.text} plate={s.plate} />;
    case "card": {
      const Card = CARDS[s.card as CardId];
      if (!Card) throw new Error(`storyboard shot "${s.id}": no card "${s.card}" in src/cards`);
      return <Card durationInFrames={shot.durationInFrames} />;
    }
    case "cast":
      return <CastShot src={s.src} speed={s.speed} rows={s.rows} castFromMs={s.castFromMs} />;
    case "receipt":
      return <ReceiptRows rows={s.rows} results={s.results} />;
  }
};

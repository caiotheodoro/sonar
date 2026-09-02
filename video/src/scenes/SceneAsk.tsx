/**
 * Beat 4: sonar ask with citations. The final scene replays
 * public/casts/ask.cast and renders the footnotes beside it. Until then the
 * beat shows the digest's top mentions, which are the citations an answer
 * resolves to, and the topic table the assistant retrieves from.
 */
import React from "react";
import { BeatPlaceholder } from "../components/BeatPlaceholder";
import { Checklist } from "../components/Panels";
import { Source } from "../components/DataPanel";
import { RESULTS } from "../manifest";

const { topMentions, topics } = RESULTS.digest;

const footnotes = topMentions
  .slice(0, 3)
  .map((m) => `[${m.mentionId.slice(0, 8)}] ${m.source} · "${m.quote}"`);

const topicLines = topics.slice(0, 3).map((t) => `${t.name} (${t.n} mentions)`);

export const SceneAsk: React.FC = () => (
  <BeatPlaceholder id="ask">
    <Checklist items={[...footnotes, ...topicLines]} />
    <Source file="results/demo/digest.json" detail="top_mentions[] · topics[]" />
  </BeatPlaceholder>
);

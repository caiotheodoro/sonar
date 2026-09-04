/** Card ids are the storyboard's vocabulary; the gate reads these keys. */
import { Audit } from "./Audit";
import { Brief } from "./Brief";
import { MapMentions } from "./MapMentions";
import { MapSentimentSov } from "./MapSentimentSov";
import { MapTopics } from "./MapTopics";
import { MapVoice } from "./MapVoice";
import { Outro } from "./Outro";
import { PicPayAbstain } from "./PicPayAbstain";
import { PriceVsBrief } from "./PriceVsBrief";
import { Ratio } from "./Ratio";
import { Reconciled } from "./Reconciled";

export const CARDS = {
  brief: Brief,
  "map-mentions": MapMentions,
  "map-sentiment-sov": MapSentimentSov,
  "map-topics": MapTopics,
  "map-voice": MapVoice,
  "price-vs-brief": PriceVsBrief,
  ratio: Ratio,
  "picpay-abstain": PicPayAbstain,
  audit: Audit,
  reconciled: Reconciled,
  outro: Outro,
} as const;

export type CardId = keyof typeof CARDS;

/** Card ids are the storyboard's vocabulary; the gate reads these keys. */
import { Audit } from "./Audit";
import { EndpointFan } from "./EndpointFan";
import { KeyFan } from "./KeyFan";
import { MentionStream } from "./MentionStream";
import { PerCallLedger } from "./PerCallLedger";
import { PriceColumn } from "./PriceColumn";
import { RunRequest } from "./RunRequest";
import { SentimentSplit } from "./SentimentSplit";
import { ShareBars } from "./ShareBars";
import { SourceGrid } from "./SourceGrid";
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
  "source-grid": SourceGrid,
  "mention-stream": MentionStream,
  "sentiment-split": SentimentSplit,
  "share-bars": ShareBars,
  "price-column": PriceColumn,
  "key-fan": KeyFan,
  "endpoint-fan": EndpointFan,
  "per-call-ledger": PerCallLedger,
  "run-request": RunRequest,
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

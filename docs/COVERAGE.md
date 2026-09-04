# COVERAGE.md — what sonar covers, in Brand24's vocabulary

Checked against brand24.com/prices on 2026-09-02 (evidence:
`results/incumbent/brand24-2026-09-02.png`). The row names are Brand24's
own source and feature names, in the order the price page lists them.
Sonar's internal source ids are in `CONTRACTS.md` §Source enum; the
mapping from Brand24's names to those ids is given per row.

Status legend:

- **covered** — sonar fetches live data for this source through a Monid
  endpoint on every `full` run, and the source appears in `basis_sources`.
- **partial** — sonar fetches a subset of what Brand24 means by the name;
  the row says which subset and what is missing.
- **not covered** — sonar fetches nothing for this source; the receipt
  lists it under `coverage_gaps` on every run.

The status column is frozen at the `docs-frozen` gate. Wave 6 (W6.2)
adds a measured column (mentions fetched, billed cost) from the frozen
demo without changing any status.

## Sources

| Brand24 source | Status | sonar source id | Reason |
|---|---|---|---|
| Facebook | partial | `facebook` | Only page reviews via `apify /apify/facebook-reviews-scraper` (`startUrls[]`, `onlyReviewsNewerThan`). Public posts, comments and groups are not fetched: no Monid endpoint returns them by keyword. |
| Instagram | partial | `instagram` | Hashtag posts via `apify /apify/instagram-hashtag-scraper` (brand hashtag, 30 per brand in `full`). Comments, stories and @-mentions in captions of other accounts are not fetched. The search-scraper is entity search and is deliberately unused. |
| X | not covered | none | No X/Twitter endpoint in the Monid catalog as of 2026-09-02 (`docs/DECISIONS.md` D008). Registered `available=False` in the provider registry; listed first in `coverage_gaps` on every receipt. |
| News | covered | `news` | `tinyfish /search` with `domain_type=news`, up to 3 pages per brand at $0, page text through `tinyfish /fetch`. Language reported as a stratum, never filtered. |
| Blogs | not covered | none | No blog-specific endpoint in the source plan. `tinyfish /search` without the news filter would return blog posts but has no blog domain type, so results could not be labelled as blogs honestly. |
| Reddit | covered | `reddit` | Posts and comments via `apify /trudax/reddit-scraper-lite` (`sort=new`, `time=month` since `docs/DECISIONS.md` D017 so the 14-day window's previous half is populated, 40 per brand in `full`). Cluster key is the post id, so comment threads are one bootstrap unit. |
| LinkedIn | not covered | none | No LinkedIn adapter in the source plan and no keyword-search endpoint for LinkedIn was inspected in the Monid catalog. |
| Medium | not covered | none | No Medium adapter in the source plan and no Medium endpoint inspected in the Monid catalog. |
| Quora | not covered | none | No Quora adapter in the source plan and no Quora endpoint inspected in the Monid catalog. |
| YouTube | covered | `youtube`, `youtube_comment` | Videos via `apify /streamers/youtube-scraper` (10 per brand, `maxResults` always set) and comments via `apify /streamers/youtube-comments-scraper` (60 per brand). Comments carry no timestamp, so they count in share of voice and sentiment but are excluded from week-over-week deltas (`no_timestamps` abstention). |
| TikTok | covered | `tiktok` | Keyword search via `apify /apidojo/tiktok-scraper` (40 per brand, `dateRange` set to the window). Video captions only; comments are not fetched. |
| Reviews | partial | `google_maps`, `trustpilot`, `g2`, `facebook` | Google Maps reviews (`apify /compass/google-maps-reviews-scraper`, 50 per brand, `maxReviews` always set), Trustpilot (`/get_company_reviews`, one call per brand) and G2 (`/get_product_reviews`, one call per brand). App Store, Google Play, Capterra, Yelp and TripAdvisor are not fetched. Ratings drive the deterministic sentiment signal. |
| Twitch | not covered | none | No Twitch adapter in the source plan; live chat has no keyword-search endpoint in the Monid catalog as inspected. |
| Newsletters | not covered | none | No newsletter adapter in the source plan; newsletter archives are not indexed by any endpoint sonar calls. |
| Podcasts | not covered | none | No podcast adapter in the source plan; transcript search is not offered by any endpoint sonar calls. |

Totals: 4 covered, 3 partial, 8 not covered, of 15 Brand24 sources.

## Demo (measured)

From the frozen demo (`results/demo/`, W6.1 — Nubank vs Itaú, C6 Bank,
PicPay, one `full` brief). Mentions are the pre-dedup count across all
four brands; cost is billed Monid USD over the four runs of that source.
Status above is unchanged.

| sonar source | Mentions (4 brands) | Billed | In `basis_sources`? |
|---|---:|---:|---|
| reddit | 69 | $0.9409 | **no** — abstained for PicPay (0 mentions), so it leaves the basis for every brand |
| instagram | 86 | $0.1710 | yes |
| tiktok | 68 | $0.0504 | yes |
| youtube | 35 | $0.1800 | yes |
| youtube_comment | 43 | $0.3893 | yes (excluded from WoW: no timestamps) |
| google_maps | 36 | $0.0317 | yes |
| facebook | 2 | $0.0190 | no — abstained `empty` for 3 of 4 brands |
| trustpilot | 0 | $0.1200 | no — the company-search lookup found no entity for any brand |
| g2 | 0 | $0.0800 | no — the software-search lookup found no product for any brand |
| news | 2 | $0.0000 | no — `empty` for 3 of 4 brands ($0 endpoint) |

The five `basis_sources` (instagram, tiktok, youtube, youtube_comment,
google_maps) carry the demo's share of voice and net sentiment. reddit's
69 mentions still feed topics and events, which are per-brand and do not
use `basis_sources`.

## AI features

| Brand24 feature | Status | sonar equivalent | Reason |
|---|---|---|---|
| Sentiment | covered | `sentiment/*`, Digest `sentiment[]` | Every relevant mention gets positive / negative / neutral from `gpt-5.6-luna`, checked against a deterministic signal (rating bucket or lexicon), with `gpt-5.6-terra` as tiebreak under the two-signal policy. Unlike Brand24, each label carries `corroboration` (confirmed / model_only / contested) and net sentiment ships with a cluster-bootstrap 95 % interval and a verdict. Portuguese and English mentions are labelled in the original language. |
| Topic analysis | covered | `topics/*`, Digest `topics[]` | Embeddings cached, average-linkage agglomerative clustering on cosine, `min_size=3`, `min_breadth=2` distinct cluster keys, three medoid exemplars per topic named by the model. Abstains with reason when embeddings fail rather than printing an empty table. |
| AI events detection | partial | `stats/events`, Digest `events[]` | Volume spikes only: a day is an event when `n_day ≥ max(5, median + 3·MAD)` and `n_clusters_day ≥ 3`, labelled by the model with one exhibit URL. Sentiment-shift events, reach-based events and the narrative Brand24 attaches to an event are not produced. |
| AI brand assistant | covered | `sonar ask <brand> "q" [--session]` | Retrieval over the session's mentions (top-20 by cosine) plus the stats summary and topic table. Every citation must resolve to a mention id and every number must occur in stats, topics or retrieved text, else the answer is marked `unverified`. Sessions are local; there is no cross-project memory and answers are English only. |

Totals: 3 covered, 1 partial, 0 not covered, of 4 Brand24 AI features.

## Brand24 features outside this table

Email alerts, influencer scoring, PDF reports and the Brand24 mobile app
are not claimed. README §Not claimed is the authoritative list; this file
only covers the source and AI-feature rows from the price page.

## Open questions

- **OQ-COV-1** LinkedIn, Medium, Quora, Twitch, Newsletters and Podcasts
  are marked not covered because no adapter exists, not because the
  Monid catalog was proven empty for them. Resolves when W3.x runs
  `monid discover -q <source>` for each and files the output under
  `docs/monid/inspect/`; a hit moves the row to partial with the endpoint
  named, a miss changes the reason to "no Monid endpoint as of <date>".
- **OQ-COV-2** The Reviews row lists the review sites sonar calls; the
  full list Brand24 aggregates under "Reviews" is not published on the
  price page. Resolves when W8.1 re-checks brand24.com and either
  finds the list (row reason updated) or records that it is unpublished.
- **OQ-COV-3** Instagram may use `apify/instagram-api-scraper` instead of
  the hashtag scraper if W3.x finds hashtag results too sparse for the
  demo brand. Resolves at W3.7 with the smoke fixture; either endpoint
  keeps the status partial.

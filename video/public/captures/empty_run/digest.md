# sonar digest — Zephyrium Bank

Competitors: none. Window: current 2026-08-28T14:08:44Z to 2026-09-04T14:08:44Z, previous 2026-08-21T14:08:44Z to 2026-08-28T14:08:44Z.

Cost verdict **RECONCILED**, total $0.2223 (Monid $0.2219, OpenAI $0.0003).

## Share of voice

Share counts mention–brand pairs over the sources that returned for every brand.

| brand | n | clusters | share | 95 % CI | WoW Δ | WoW CI | verdict | basis |
|---|---|---|---|---|---|---|---|---|
| Zephyrium Bank | 0 | 0 | — | — | — | — | ABSTAIN | google_maps |

## Sentiment

| brand | n | confirmed | pos | neg | neu | net | 95 % CI | iid CI | design effect | WoW Δ | WoW CI | confirmed-only CI | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Zephyrium Bank | 0 | 0 | 0 | 0 | 0 | — | — | — | — | — | — | — | ABSTAIN |

## By source

| brand | source | n | clusters | net | 95 % CI | design effect | WoW scope |
|---|---|---|---|---|---|---|---|
| Zephyrium Bank | google_maps | 0 | 0 | — | — | — | yes |

## Topics

None.

## Events

None.

## Top mentions

None.

## Abstentions

| scope | brand | source | reason | detail |
|---|---|---|---|---|
| source | Zephyrium Bank | reddit | empty | zero mentions after parse |
| source | Zephyrium Bank | youtube | empty | local_seq 2: 1 item(s), all provider errors: NO_VIDEOS |
| source | Zephyrium Bank | youtube_comment | empty | no videos to fetch comments for |
| source | Zephyrium Bank | tiktok | empty | zero mentions after parse |
| source | Zephyrium Bank | instagram | schema_drift | local_seq 4: apify /apify/instagram-hashtag-scraper: item 0: required key 'caption' absent; raw saved 4.json |
| source | Zephyrium Bank | facebook | empty | local_seq 6: 1 item(s), all provider errors: not_available |
| source | Zephyrium Bank | trustpilot | empty | lookup found no matching entity; reviews run skipped |
| source | Zephyrium Bank | g2 | empty | lookup found no matching entity; reviews run skipped |
| source | Zephyrium Bank | news | empty | zero mentions after parse |
| brand | Zephyrium Bank | — | below_minimum | net: n=0 < 20 in current; n_clusters=0 < 5 in current; n=0 < 20 in previous; n_clusters=0 < 5 in previous |
| brand | Zephyrium Bank | — | below_minimum | share: n=0 < 20 in current; n_clusters=0 < 5 in current; n=0 < 20 in previous; n_clusters=0 < 5 in previous |
| brand | Zephyrium Bank | google_maps | degenerate | by_source google_maps net: no relevant mentions |
| topics | Zephyrium Bank | — | below_minimum | no topics: 0 relevant mentions, min_size 3 |

## Coverage gaps

| source | reason | note |
|---|---|---|
| x | unavailable | X/Twitter has no Monid endpoint (verified 2026-09-02) |

## Narration

No narration for this run.

# sonar receipt — Zephyrium Bank

> **RECONCILED** — every run with an id is priced from `GET /v1/runs` and no remote run is unmatched.

| Field | Value |
|---|---|
| Session | 20260904T140844Z-zephyrium-bank-2e23b9 |
| Verdict | **RECONCILED** |
| Profile | lite |
| Competitors | none |
| Sources | reddit, youtube, youtube_comment, tiktok, instagram, google_maps, facebook, trustpilot, g2, news |
| Started | 2026-09-04T14:08:44Z |
| Finished | 2026-09-04T14:13:15Z |
| Reconciled | 2026-09-04T14:13:15Z |
| schema_rev | 1.1.2 |
| sonar_rev | 0.1.0+2a8bfbb |

## Price side by side

|  | Brand24 Team | sonar |
|---|---|---|
| Price | $349 per month | $0.2223 this brief |
| Monthly equivalent | $349 | $0.8892 at 4 briefs |
| Mentions | 10,000 quota | 2 this brief |
| Ratio | 1× | 392.5× |
| Price checked | 2026-09-02 | 2026-09-04T14:13:15Z |

## Totals

| Line | Value |
|---|---|
| Monid billed | $0.2219 |
| Monid runs | 9 |
| Monid runs billed | 8 |
| Monid runs with zero results | 3 |
| Monid runs failed | 0 |
| ElevenLabs (breakout of Monid) | $0.0000 |
| OpenAI | $0.0003 |
| OpenAI calls | classify 1 |
| OpenAI tokens | 789 |
| **Total** | **$0.2223** |

## Runs

Every Monid call of the session, including calls that returned no id, runs that returned zero results and runs that cost nothing.

| seq | run id | endpoint | brand | source | status | results | estimate | billed | cost source |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 01M1PC07SJ2R9Q4DZM845A7B60 | apify /trudax/reddit-scraper-lite | Zephyrium Bank | reddit | COMPLETED | 19 | $0.1340 | $0.1483 | /v1/runs |
| 2 | 01M1PC07VE9BTNBNNDV8T1K7JS | apify /streamers/youtube-scraper | Zephyrium Bank | youtube | COMPLETED | 1 | $0.0225 | $0.0045 | /v1/runs |
| 3 | 01M1PC07VSF18T82XQD5133WQP | apify /apidojo/tiktok-scraper | Zephyrium Bank | tiktok | COMPLETED | 20 | $0.0090 | $0.0090 | /v1/runs |
| 4 | 01M1PC07S856XH6F779KYE92X7 | apify /apify/instagram-hashtag-scraper | Zephyrium Bank | instagram | COMPLETED | 1 | $0.0035 | $0.0035 | /v1/runs |
| 5 | 01M1PC07WEF0GY5T3RPSYVQYRC | apify /compass/google-maps-reviews-scraper | Zephyrium Bank | google_maps | COMPLETED | 4 | $0.0169 | $0.0027 | /v1/runs |
| 6 | 01M1PC07W1321DSMCJ035X5DXM | apify /apify/facebook-reviews-scraper | Zephyrium Bank | facebook | COMPLETED | 1 | $0.0460 | $0.0040 | /v1/runs |
| 7 | 01M1PC0CE1V7AS2GR15RF4PGKW | trustpilot /search_companies | Zephyrium Bank | trustpilot | COMPLETED | 0 | $0.0300 | $0.0300 | /v1/runs |
| 8 | 01M1PC0G5D11KY2WJBCD4EEPX1 | g2 /search_software | Zephyrium Bank | g2 | COMPLETED | 0 | $0.0200 | $0.0200 | /v1/runs |
| 9 | 01M1PC0R2SDS39HD92V99MFKRV | tinyfish /search | Zephyrium Bank | news | COMPLETED | 0 | $0.0000 | $0.0000 | /v1/runs |

## Reconciliation

| Field | Value |
|---|---|
| Fetched `GET /v1/runs` | 2026-09-04T14:13:15Z |
| Listed in window | 9 |
| Unmatched remote run ids | none |
| Unreconciled local_seq | none |

## Mentions

| Field | Value |
|---|---|
| Fetched | 2 |
| After dedup (rows, one per brand) | 2 |
| Labelled | 2 |
| Excluded | dedup_native_id 0, dedup_text 0, dedup_url 0, error 0, irrelevant_label 0, not_about_brand 2, refused 0, unparseable 0 |
| By source | google_maps 2 |
| By brand | Zephyrium Bank 2 |

## Audit (classifier vs tiebreak, fixed 10 % sample)

| Field | Value |
|---|---|
| Sample size | 0 |
| Agree | 0 |
| Agreement | — |
| Tiebreak calls | 0 |
| Tiebreak overflow (40 % cap) | 0 |

## Abstentions

| scope | brand | source | reason | detail |
|---|---|---|---|---|
| source | Zephyrium Bank | reddit | empty | zero mentions after parse |
| source | Zephyrium Bank | youtube | empty | local_seq 2: 1 item(s), all provider errors: NO_VIDEOS |
| source | Zephyrium Bank | youtube_comment | empty | no videos to fetch comments for |
| source | Zephyrium Bank | tiktok | empty | zero mentions after parse |
| source | Zephyrium Bank | instagram | schema_drift | local_seq 4: apify /apify/instagram-hashtag-scraper: item 0: required key 'caption' absent; raw saved 4.json |
| source | Zephyrium Bank | facebook | empty | local_seq 6: 1 item(s), all provider errors: not_available |
| source | Zephyrium Bank | trustpilot | empty | lookup found no matching entity; reviews run skipped |
| source | Zephyrium Bank | g2 | empty | lookup found no matching entity; reviews run skipped |
| source | Zephyrium Bank | news | empty | zero mentions after parse |

## What could not be checked

- X/Twitter: no Monid endpoint
- reddit: 19 result(s) skipped, no brand match

content_digest: `2d379690b2b153ecb311d4c7f7b1ee0faf614390c67f5ca3f4242f74e4acc2bb`


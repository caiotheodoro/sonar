# Incumbent price evidence: Brand24

- `brand24-2026-09-02.png` — full-page screenshot of https://brand24.com/prices/ taken 2026-09-02 (Playwright, CSS scale). Plans visible: Individual $249/mo, Team $349/mo ($299/mo billed annually), Pro $499/mo, Business $699/mo, Enterprise from $1,499/mo. Team = 10K mentions/month.
- `../../video/public/shots/brand24-pricing.png` — second dated capture, 2026-09-04, viewport 1920×1080 with the Monthly tab selected (`video/capture/shoot.mjs`, Playwright); Team $349/mo visible. Its sidecar `../../video/public/shots/brand24-pricing.json` records url, date and viewport. The video quotes the tier prices from `video/src/data/external-facts.json`, each tied to this capture.
- `archive-url.txt` — the closest Wayback Machine snapshot and the log of save requests. 2026-09-02: `web.archive.org/save` timed out. 2026-09-04 (W8.1): the save request returned HTTP 200 but the availability API still reported the 2026-08-12 snapshot as closest when this was written; the dated PNGs are the primary evidence either way.

The single source of the price inside the code is `report/incumbent.py`; the published-claims test asserts README, this file and `results/demo/receipt.json` agree with it.

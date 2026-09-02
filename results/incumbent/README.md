# Incumbent price evidence: Brand24

- `brand24-2026-09-02.png` — full-page screenshot of https://brand24.com/prices/ taken 2026-09-02 (Playwright, CSS scale). Plans visible: Individual $249/mo, Team $349/mo ($299/mo billed annually), Pro $499/mo, Business $699/mo, Enterprise from $1,499/mo. Team = 10K mentions/month.
- `archive-url.txt` — the closest Wayback Machine snapshot at the time of writing. A fresh `web.archive.org/save` request on 2026-09-02 timed out; the re-check task (W8.1) retries it.

The single source of the price inside the code is `report/incumbent.py`; the published-claims test asserts README, this file and `results/demo/receipt.json` agree with it.

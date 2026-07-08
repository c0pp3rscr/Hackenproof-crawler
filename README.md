# HackenProof Crawler

Crawls every bug-bounty program listed on [HackenProof](https://hackenproof.com/programs)
and exports the participation requirements to a sortable Excel workbook.

For each program it captures:

| Column | Source field | Meaning |
| --- | --- | --- |
| **Reputation Required** | `minReputation` | Minimum reputation points needed to participate (numeric, sortable) |
| **KYC Required** | `kycRequired` | Whether KYC is required (Yes/No) |
| **PoC Required** | `pocRequired` | Whether a proof-of-concept is required (Yes/No) |
| **Submission Fee ($)** | `submissionFee` | Deposit/fee (USD) a hacker must pay to submit a report (numeric, sortable; blank = none) |
| **Deposit Available** | `depositAvailable` | Whether the program has a guaranteed reward deposit (Yes/No) — a distinct field from the submission fee |

Plus context columns: Program, Company, Max Reward, Status, Activity, Slug, URL.

The output sheet has frozen headers and an auto-filter on every column, so you can
sort/filter by reputation, KYC, PoC, or deposit directly in Excel/Google Sheets.

## How it works

- Programs are enumerated from the public `sitemap.xml` (~320 programs).
- Each program's requirements are read from the server-rendered `__NUXT_DATA__`
  payload on its detail page (HackenProof is a Nuxt 3 app). See [src/nuxt.py](src/nuxt.py)
  for the devalue decoder.
- Requests are made with a Googlebot user-agent, which HackenProof allow-lists for
  SEO, so pages are returned fully rendered instead of a Cloudflare challenge.

## Install

```bash
pip install -r requirements.txt
```

Requires Python 3.9+.

## Usage

```bash
# Crawl all programs -> hackenproof_programs.xlsx
python src/main.py

# Custom output path
python src/main.py -o programs.xlsx

# Quick test run (first 20 programs only)
python src/main.py --limit 20

# Tune concurrency (default 8)
python src/main.py --workers 12
```

A full crawl of ~320 programs takes roughly 30 seconds.

## Project layout

| File | Purpose |
| --- | --- |
| [src/main.py](src/main.py) | CLI entry point |
| [src/crawler.py](src/crawler.py) | Sitemap enumeration + detail fetch/parse |
| [src/nuxt.py](src/nuxt.py) | Decoder for Nuxt's `__NUXT_DATA__` (devalue format) |
| [src/excel.py](src/excel.py) | Writes the sortable `.xlsx` workbook |

## Notes

- If HackenProof tightens its Cloudflare rules and the Googlebot user-agent stops
  working, the crawler will report programs that failed to parse
  (`NuxtDataNotFound`). In that case a browser-based fetch (e.g. Playwright) would be
  needed to solve the challenge.
- Programs that redirect (a renamed slug) are followed and de-duplicated on their
  canonical slug.

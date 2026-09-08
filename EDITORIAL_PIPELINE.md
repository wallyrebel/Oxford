# Oxford editorial pipeline — September 8, 2026

Every candidate passes **extract → rewrite → check**. A useful short notice is allowed;
the default **200-word minimum is a soft writing target**, never a publication quota.
Use all relevant source details to make longer articles when possible. Do not pad or
invent background, quotes, future updates, dates, district names or reopening days.

| Stage | Default model | Input / output price per million tokens |
|---|---|---|
| Extract facts and verbatim supporting evidence | `gpt-4.1-nano` | $0.10 / $0.40 |
| Write the headline, excerpt and article | `gpt-5.6-luna` | $0.20 / $1.20 |
| Independently compare every claim with the original source | `gpt-5.4-mini` | $0.75 / $4.50 |

Prices checked against [nano](https://developers.openai.com/api/docs/models/gpt-4.1-nano),
[Luna](https://developers.openai.com/api/docs/models/gpt-5.6-luna) and
[mini](https://developers.openai.com/api/docs/models/gpt-5.4-mini) documentation.
An illustrative article using 1,400/300 extraction tokens, 2,200/650 rewrite tokens
and 2,400/180 checking tokens costs about **$0.0041** in model tokens. Actual usage,
retries, source length and prices vary; logs record input/output tokens for each stage.
This excludes GitHub Actions, feed services and image providers.

## Required publication fields

Each published article must have a category, tags, and an uploaded featured image.
The eight existing feed URLs and names remain. Categories and source-specific tags
now match school/city/police, county, statewide, and Oxford sports coverage.

Images are tried in this order: **RSS/source image → Pexels → Unsplash**. Provider
credentials remain in GitHub secrets. No key is copied into code. A failed download
or upload defers publication for another run. Stock photographs carry a visible
illustration label and are not represented as images of the reported event.

## Publishing cadence and safeguards

- Checks run four times per hour at minutes 7, 22, 37 and 52 UTC, allowing multiple
  articles daily when valid fresh sources are available. There is no one-post-per-day cap.
- Up to five approved stories per feed per run. Duplicates and rejected sources do
  not consume those five slots. The existing 48-hour source window stays in place.
- Source failures are rejected before model calls. The extraction stage must quote
  evidence actually present in the source. The checking stage receives the original
  source, not merely the extraction model's interpretation.
- A rejected draft gets at most one correction attempt, then the same independent
  checker reviews every sentence against the original source again. This adds bounded
  token cost only when a correction is attempted.
- Ambiguous or unsupported drafts are withheld. Shortness alone is not a rejection.
- Rejected source fingerprints are stored separately from published entries to avoid
  paying for the same failed source every 15 minutes. Changed text is reconsidered.
- `python -m rss_to_wp review` lists rejected sources and reasons. These need an editor;
  an automated evidence check is not a guarantee of real-world truth.
- API failures, incomplete outputs, duplicate-lookup failures, missing images and
  failed metadata creation do not produce a public article. Operational failures retry.
- Only escaped paragraph text becomes editorial HTML. Source instructions cannot
  authorize changes to prompts or checks. Claims, names, numbers and quotes are checked.
- Dry runs never consume publication history. Publishing jobs are serialized separately from preview jobs; the SQLite
  database is cached even after partial failure, with 30-day recovery artifacts.
- Manual verification runs do not send the scheduled publication-summary emails.

## Settings and verification

Repository **variables** `OPENAI_EXTRACTION_MODEL`, `OPENAI_REWRITE_MODEL`,
`OPENAI_CHECK_MODEL`, `TARGET_MIN_WORDS` and `TIMEZONE` override workflow defaults.
The legacy `OPENAI_MODEL` secret no longer silently forces the old single-pass model.
For local runs the rewrite setting remains `OPENAI_MODEL` in `.env`; see `.env.example`.
The API key, WordPress application password and image-provider secrets are preserved.

Run `python -m pytest -q` before deployment. CI runs the same regression tests on a
pull request and before every publishing run. First run Actions manually with
`dry_run=true`, optionally selecting one feed. Inspect its results, then enable
scheduled publication and inspect a published article's fields and source support.

To roll back code, revert the deployment commit/PR. Keep `data/processed.db`; reverting
or deleting publication history can cause duplicate work. Rejected entries are an
additive table, compatible with the old database. The old schedule remains recoverable
in Git history. Reverting code restores the old weaker editorial checks.

## Scheduler recovery on September 8, 2026

Use **Oxford News Publisher** (`.github/workflows/publish_news.yml`) in Actions.
The previous `rss_to_wp.yml` registration stopped starting jobs even when active;
normal and force-cancel returned HTTP 409 for its ghost queued runs. Refreshing
its enabled state did not repair dispatch. A freshly registered workflow started
immediately. Historical run records are retained for diagnosis.

The replacement keeps the four hourly checks, existing accounts/secrets, feeds,
cache keys and recovery artifacts. Concurrency applies to the job, with separate
preview and publication groups. A preview cannot hold the production queue.
Do not re-enable the retired workflow or run a second publisher in parallel.
The branch-only push trigger used to verify recovery was removed before deployment.

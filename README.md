# Resend AI Model Briefing

A security-focused Python CLI that collects official AI company announcements, asks OpenAI to
produce a cited briefing, and delivers it to a Resend Segment as a Broadcast.

The briefing includes:

- one model recommendation for the day or week, with use cases and tradeoffs;
- up to five important model announcements;
- up to three broader signals inferred from the supplied announcements;
- source links for every recommendation, news item, and signal.

This project has no web server, public subscription form, database, or Namecheap runtime. It runs
locally or as a scheduled GitHub Actions job.

## Sources

The default catalog is [`config/sources.yaml`](config/sources.yaml):

| Company | Official source type |
| --- | --- |
| OpenAI | RSS |
| Anthropic | Sitemap |
| Google DeepMind | RSS |
| Meta AI | HTML index |
| xAI | HTML index |
| Mistral AI | RSS |
| Nous Research | HTML releases |

Sources can be enabled, disabled, or replaced without changing Python code.

## How it works

1. The CLI loads and strictly validates the source catalog.
2. A restricted HTTP client downloads only explicitly allowed HTTPS hosts and paths.
3. RSS, Atom, sitemap, and HTML documents are parsed with size and content limits.
4. Recent, complete announcements are sent to the OpenAI Responses API as untrusted source data.
5. OpenAI returns a typed briefing. The CLI rejects unknown citations and oversized content.
6. The content is HTML-escaped and delivered through a Resend Broadcast with Resend's managed
   unsubscribe URL.

If no recent announcements are available, the run exits successfully without calling OpenAI or
sending a Broadcast.

## Requirements

- A Resend account with a verified sending domain and a Segment.
- A dedicated Resend API key. Broadcast creation and contact management require full access, so
  keep this key limited to this project, store it only as a secret, and rotate it if exposed.
- An OpenAI API key.
- [`uv`](https://docs.astral.sh/uv/getting-started/installation/).

## Local setup

Clone the repository, then create your local environment file:

```bash
cp .env.example .env
```

Fill in `.env`:

```dotenv
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-6-luna
RESEND_API_KEY=re_...
RESEND_FROM=AI Model Briefing <briefing@your-domain.example>
RESEND_SEGMENT_ID=00000000-0000-0000-0000-000000000000
BRIEFING_MODE=daily
SOURCES_FILE=config/sources.yaml
```

Validate everything with one command. `uv` creates the virtual environment and installs the exact
locked dependencies automatically:

```bash
uv run --locked ai-model-briefing check
```

Generate a local HTML preview without contacting Resend:

```bash
uv run --locked ai-model-briefing preview
```

The default output is `briefing-preview.html`. Preview mode needs the OpenAI variables but does not
require Resend configuration.

## Subscriber management

There is intentionally no public signup endpoint. Add a contact only after receiving explicit
consent:

```bash
uv run --locked ai-model-briefing subscribe reader@example.com --consent-confirmed
```

Globally unsubscribe an existing Resend contact:

```bash
uv run --locked ai-model-briefing unsubscribe reader@example.com
```

Every delivered email also includes Resend's managed unsubscribe link. Resend automatically skips
globally unsubscribed contacts in later Broadcasts.

## Send a briefing locally

This command performs the complete flow and immediately sends a Broadcast to the configured
Segment:

```bash
uv run --locked ai-model-briefing run
```

Use `preview` first when changing the prompt, renderer, model, or sources.

## GitHub Actions setup

The repository contains two workflows:

- `CI` runs formatting, linting, type checks, and tests without secrets.
- `Send AI model briefing` runs manually or on the configured daily/weekly schedule.

Add these repository Actions secrets:

- `OPENAI_API_KEY`
- `RESEND_API_KEY`
- `RESEND_FROM`
- `RESEND_SEGMENT_ID`

Optional repository variables:

- `OPENAI_MODEL` defaults to `gpt-6-luna` for a cost-efficient scheduled briefing.
- `BRIEFING_MODE` defaults to `daily`; set it to `weekly` to use the Monday schedule.

The scheduled workflow uses `America/Monterrey`. Change the cron expressions and timezone in
`.github/workflows/briefing.yml` for a different delivery time. Workflow concurrency prevents two
deliveries from running at the same time, but manually rerunning a completed delivery can create a
second Broadcast.

## Customize sources

Each source entry supports:

```yaml
- id: example-ai
  company: Example AI
  type: rss # rss, sitemap, or html
  url: https://example.com/news/rss.xml
  allowed_hosts: [example.com]
  include_paths: [/news/]
  enabled: true
  max_items: 10
```

All URLs must use HTTPS. Redirects, article links, DNS results, response types, and response sizes
are checked before content is accepted. Keep `allowed_hosts` and `include_paths` as narrow as
possible.

## Commands

```text
ai-model-briefing --help
ai-model-briefing check
ai-model-briefing preview [--output PATH]
ai-model-briefing run
ai-model-briefing subscribe EMAIL --consent-confirmed
ai-model-briefing unsubscribe EMAIL
```

## Development

```bash
uv sync --locked --all-groups
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest
```

Tests use local fixtures and mocked transports. They do not call OpenAI, Resend, or the configured
news sources.

## Security notes

- `.env`, virtual environments, caches, and generated previews are ignored by Git.
- OpenAI responses use `store=False`.
- Remote news text is treated as untrusted data and cannot supply model instructions.
- Model-generated HTML is escaped before delivery.
- Secrets are never printed by `check` or normal error handling.
- GitHub Actions permissions are read-only and external actions are pinned to immutable commit
  SHAs.
- Dependency versions and hashes are committed in `uv.lock`.

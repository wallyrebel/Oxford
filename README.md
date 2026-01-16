# RSS to WordPress Automation

Automated RSS feed monitoring, AI-powered article rewriting, and WordPress publishing.

## Features

- **RSS Feed Monitoring**: Parse RSS/Atom feeds with robust error handling
- **AI Rewriting**: Convert press releases to AP-style news articles using GPT-5 mini
- **Smart Deduplication**: SQLite-based tracking ensures no duplicate posts
- **Image Handling**: 
  - Extract images from RSS (media:content, enclosures, HTML)
  - Fallback to Pexels/Unsplash for stock photos
  - Proper attribution in alt text
- **WordPress Publishing**: Full REST API integration with categories and tags
- **Scheduling**: GitHub Actions (every 15 min) or VPS cron/systemd

## Quick Start

### 1. Clone and Install

```bash
git clone https://github.com/yourusername/tippahnews-auto.git
cd tippahnews-auto

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate   # Windows

# Install dependencies
pip install -r requirements.txt
pip install -e .
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your API keys
```

**Required variables:**
- `OPENAI_API_KEY` - Your OpenAI API key
- `WORDPRESS_BASE_URL` - Your WordPress site URL
- `WORDPRESS_USERNAME` - WordPress username
- `WORDPRESS_APP_PASSWORD` - [Generate an Application Password](https://make.wordpress.org/core/2020/11/05/application-passwords-integration-guide/)

**Optional variables:**
- `PEXELS_API_KEY` - For fallback images ([Get key](https://www.pexels.com/api/))
- `UNSPLASH_ACCESS_KEY` - For fallback images ([Get key](https://unsplash.com/developers))

### 3. Configure Feeds

Edit `feeds.yaml`:

```yaml
feeds:
  - name: "Local News"
    url: "https://example.com/rss"
    default_category: "News"
    default_tags:
      - "Local"
    max_per_run: 5
```

### 4. Run

```bash
# Full run
python -m rss_to_wp run --config feeds.yaml

# Dry run (no publishing)
python -m rss_to_wp run --config feeds.yaml --dry-run

# Single feed only
python -m rss_to_wp run --config feeds.yaml --single-feed "Local News"

# Check status
python -m rss_to_wp status
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `run` | Process feeds and publish to WordPress |
| `status` | Show processed entry count and recent entries |
| `clear-db` | Clear the deduplication database |

### Run Options

| Option | Description |
|--------|-------------|
| `--config`, `-c` | Path to feeds.yaml (default: feeds.yaml) |
| `--dry-run`, `-n` | Process without publishing |
| `--single-feed`, `-f` | Process only named feed |
| `--hours`, `-h` | Time window in hours (default: 48) |

## Feed Configuration

```yaml
feeds:
  - name: "Feed Name"              # Required: Display name
    url: "https://..."             # Required: RSS/Atom URL
    default_category: "News"       # Optional: WordPress category
    default_tags:                  # Optional: Tags to apply
      - "Tag1"
      - "Tag2"
    max_per_run: 5                 # Optional: Max entries per run (default: 5)
    use_original_title: false      # Optional: Keep original title (default: false)
```

## GitHub Actions Setup

The workflow runs every 15 minutes automatically.

### Required Secrets

Go to **Settings > Secrets and variables > Actions** and add:

| Secret | Required | Description |
|--------|----------|-------------|
| `OPENAI_API_KEY` | ✅ | OpenAI API key |
| `WORDPRESS_BASE_URL` | ✅ | Site URL (e.g., `https://example.com`) |
| `WORDPRESS_USERNAME` | ✅ | WordPress username |
| `WORDPRESS_APP_PASSWORD` | ✅ | Application password |
| `PEXELS_API_KEY` | ❌ | Pexels API key |
| `UNSPLASH_ACCESS_KEY` | ❌ | Unsplash access key |
| `TIMEZONE` | ❌ | Timezone (default: UTC) |

### Manual Trigger

You can manually trigger the workflow from the Actions tab with options for dry-run and single-feed.

## VPS/Cron Deployment

### Using Cron

```bash
# Edit crontab
crontab -e

# Add (runs every 15 minutes)
*/15 * * * * cd /path/to/project && /path/to/.venv/bin/python -m rss_to_wp run --config feeds.yaml >> /var/log/rss-to-wp.log 2>&1
```

### Using Systemd

Create `/etc/systemd/system/rss-to-wp.service`:

```ini
[Unit]
Description=RSS to WordPress Automation
After=network.target

[Service]
Type=oneshot
User=www-data
WorkingDirectory=/path/to/project
EnvironmentFile=/path/to/project/.env
ExecStart=/path/to/.venv/bin/python -m rss_to_wp run --config feeds.yaml

[Install]
WantedBy=multi-user.target
```

Create `/etc/systemd/system/rss-to-wp.timer`:

```ini
[Unit]
Description=Run RSS to WordPress every 15 minutes

[Timer]
OnBootSec=5min
OnUnitActiveSec=15min

[Install]
WantedBy=timers.target
```

Enable:

```bash
sudo systemctl enable rss-to-wp.timer
sudo systemctl start rss-to-wp.timer
```

## Project Structure

```
.
├── src/rss_to_wp/
│   ├── __init__.py
│   ├── __main__.py
│   ├── cli.py              # CLI commands
│   ├── config.py           # Configuration models
│   ├── feeds/              # RSS parsing & filtering
│   ├── images/             # Image extraction & fallbacks
│   ├── rewriter/           # OpenAI AP-style rewriting
│   ├── storage/            # SQLite deduplication
│   ├── utils/              # Logging & HTTP utilities
│   └── wordpress/          # WP REST API client
├── data/                   # Runtime data (gitignored)
│   └── processed.db
├── .github/workflows/
│   └── rss_to_wp.yml
├── feeds.yaml
├── .env.example
├── pyproject.toml
├── requirements.txt
└── README.md
```

## Troubleshooting

### Common Issues

**"Config file not found"**
- Ensure `feeds.yaml` exists in the working directory

**"Error loading settings"**
- Check `.env` file exists and has required variables
- Verify no typos in environment variable names

**"WordPress authentication failed"**
- Verify Application Password is correct (no spaces in password)
- Ensure user has publishing permissions

**"No entries found"**
- Check if RSS feed URL is accessible
- Verify entries are within 48-hour window

### Debug Mode

```bash
LOG_LEVEL=DEBUG python -m rss_to_wp run --config feeds.yaml
```

## License

MIT License

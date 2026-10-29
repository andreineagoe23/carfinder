# carfinder

Find a used car across the big **German and Romanian** marketplaces from **one search
form**. Pick a make, then one model or *All models*, and set your limits. You get every
matching listing in one ranked list, with prices as listed. Each listing is scored,
de-duplicated across sites and flagged for anything suspicious.

**Web app:** `https://<your-github-user>.github.io/carfinder/`

| | Site | Sellers | How it's covered |
|---|---|---|---|
| 🇩🇪 | [mobile.de](https://www.mobile.de) | Mostly dealers | Pre-filtered link (blocks automated reading) |
| 🇩🇪 | [AutoScout24](https://www.autoscout24.de) | Mostly dealers, with a price rating | **Listings shown in the app** |
| 🇩🇪 | [Kleinanzeigen](https://www.kleinanzeigen.de) | Mostly private | **Listings shown in the app** |
| 🇷🇴 | [Autovit](https://www.autovit.ro) | Mostly dealers | **Listings shown in the app** |
| 🇷🇴 | [OLX.ro](https://www.olx.ro) | Mostly private | Link: make, model, year and price (blocks automated reading) |
| 🇷🇴 | [Publi24](https://www.publi24.ro) | Private classifieds | Link: make, model and fuel (other URL filters are unreliable) |
| 🇷🇴 | [AutoUncle.ro](https://www.autouncle.ro) | Collects Romanian ads and rates the price | Link: make and model |

German sites search around a zip code. Romanian sites search the whole country. Prices
in lei are converted to euros at the day's ECB rate, and the card also shows the
listed amount.

## How it works

```
GitHub Pages (site/)                GitHub Actions                     results branch
┌──────────────────────┐  dispatch  ┌────────────────────────┐  push  ┌──────────────────────┐
│ form → site links    │ ─────────▶ │ carfinder search       │ ─────▶ │ index.json           │
│ "Search & show cars" │            │  fetch AS24 + KA       │        │ searches/<id>.json   │
│ results grid         │ ◀───────── │  dedupe · score · save │        └──────────────────────┘
└──────────────────────┘   read     └────────────────────────┘                 ▲
                                    refresh.yml (twice a day) ─────────────────┘
                                      + optional Telegram alerts
```

- The **site** is static HTML/JS. It builds the search links itself. To get listings, it
  starts the `search` workflow through the GitHub API and then reads the results back
  from the `results` branch.
- The **Python package** (`src/carfinder`) does the fetching, merging and scoring. It is
  also a CLI you can run locally.
- **Searches you have run** are re-run twice a day by `refresh.yml`, which tracks new cars and
  price drops.

## Set up your own copy

1. **Fork or push this repo** to your GitHub account.
2. **Enable Pages:** *Settings → Pages → Source: GitHub Actions*. The `pages` workflow
   deploys `site/` on every push to `main`.
3. **Create a token** so the site can start searches:
   [new fine-grained token](https://github.com/settings/personal-access-tokens/new) →
   *Only select repositories*: this repo → *Permissions*: **Actions: Read and write**,
   **Contents: Read-only**.
4. Open the site, click **Settings** and paste the token. It is kept in your browser's
   local storage only.
5. Optional **Telegram alerts** for new cars: create a bot with
   [@BotFather](https://t.me/BotFather), then add the repository secrets
   `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`.

> GitHub pauses scheduled workflows in repos with no activity for 60 days. Running a
> search from the site, or any push, counts as activity.

## Scoring

Each car gets a score from 0 to 100, built from:

- **Price vs. similar cars** in the same search: same model, same year ±1. In an
  *All models* search, Kleinanzeigen ads get their model guessed from the title.
- **Kilometres per year**
- **AutoScout24's own price rating** (top / good / fair price)
- **Seller type:** dealers in Germany owe 12 months' warranty (*Gewährleistung*)
- **Photos:** a listing without any loses points

Flags warn about:

- Prices far below market
- High mileage per year
- Damage words in the title (*Unfall*, *Schaden*, *defekt*, *Bastler*, ...)
- Private sellers
- Price reductions

The same car listed on several sites is merged into one card, with an "Also on" link to
the other site. In the results you can filter by country and by seller type (dealer or
private).

## Command line

Requires [uv](https://docs.astral.sh/uv/).

```sh
uv sync
uv run carfinder links mazda-cx3 --open     # open the pre-filtered search on every site
uv run carfinder search mazda-cx3           # fetch, score and save to ./results
uv run carfinder refresh                    # re-run every saved search
uv run carfinder catalog                    # rebuild site/data/catalog.json (makes & models)
```

Profiles for the CLI live in [`profiles/`](profiles/) as YAML. See
[`mazda-cx3.yaml`](profiles/mazda-cx3.yaml).

## Development

```sh
uv run pytest                       # Python tests
node --test tests/js/*.test.mjs     # JS link-builder tests (same URLs as Python)
cd site && python3 -m http.server   # preview the UI at http://localhost:8000
```

```
site/                    static web app (GitHub Pages)
  js/links.js            per-site search URL builders (mirror of sites/*.py)
  js/github.js           GitHub API: start workflow, read results
  js/app.js              UI
  data/catalog.json      makes/models with mobile.de IDs
src/carfinder/
  sites/                 one module per marketplace: link builder + fetcher/parser
  catalog.py             make/model catalog; guesses the model from ad titles
  search.py              one run: fetch → dedupe → score → save
  dedupe.py, scoring.py, store.py, notify.py, catalog.py
  cli.py
.github/workflows/       search (from the UI), refresh (scheduled), pages, ci
scripts/results-branch.sh
```

To add a site, subclass `Site` in `src/carfinder/sites/`, register it in
`sites/__init__.py`, and add a matching builder to `site/js/links.js`.

## Fair use

This is a personal tool, kept to a human pace:

- It reads at most a few result pages per site per search, with a delay between pages.
- It identifies itself honestly in the User-Agent and doesn't try to get around bot
  protection.
- It only requests paths that the sites' `robots.txt` allow.
- mobile.de and OLX block automated access, so carfinder only links to them.
- Autovit's robots.txt rules out price parameters, so the price filter is applied
  after the page is fetched.

Respect each site's terms of use. carfinder is not affiliated with any of these
marketplaces, and its scores are a starting point, not advice. Always have the car
inspected before you pay.

## License

[MIT](LICENSE)

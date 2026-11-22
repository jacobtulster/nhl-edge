# NHL Edge

A shared website that updates itself with **model win probabilities**, **sportsbook moneylines**, and **expected value (EV)** — same blueprint as NBA Edge.

You and your friend just open the link. No Colab. No manual refresh every hour.

## How to use it

1. Open the GitHub Pages URL for this repo
2. Read the board and the **Tracked +EV ROI** section under it

The model shows **likelihoods**, not guaranteed winners.  
**EV** = model probability × decimal odds − 1 (best available US book **moneyline**).

Each hourly run auto-logs topsides with **EV ≥ 0** into `docs/picks.json`, grades them when BallDontLie marks the game final, and updates the ROI equity curve (green above zero / red below).

## What runs in the background

Every hour from **8:00 AM to 11:00 PM Eastern**:

1. Update the games database (BallDontLie NHL API)
2. Train/score Model B (moneyline)
3. Pull live moneylines (The Odds API `icehockey_nhl`)
4. Publish `docs/ev_board.json` + `docs/picks.json`

Overnight hours are skipped on purpose.

## One-time setup

### 1. Put this on GitHub

Create a repo, push this project, and invite your friend as a collaborator if you want.

### 2. Add API keys (Secrets)

Repo → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

| Secret name | Where to get it |
|-------------|-----------------|
| `BALLDONTLIE_API_KEY` | https://app.balldontlie.io/account (NHL games need a tier that includes NHL) |
| `ODDS_API_KEY` | https://dash.the-odds-api.com/ |

### 3. Turn on GitHub Pages

Repo → **Settings** → **Pages**

- Source: **Deploy from a branch**
- Branch: `main`
- Folder: `/docs`

Your site will be: `https://<your-username>.github.io/nhl-edge/`

### 4. First run

Repo → **Actions** → **NHL Edge hourly pipeline** → **Run workflow**

## Run locally (optional)

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# put your keys in .env

python scripts/pipeline.py --force
```

## Notes

- v1 is **NHL moneyline EV only** (Model B Elo + rolling margins, same structure as NBA Edge).
- The research Colab (`NHL_Edge.ipynb`) is the longer-term feature lab; this repo is the live board.

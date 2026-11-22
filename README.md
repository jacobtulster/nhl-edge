# NHL Edge

A shared website that updates itself with **model cover probabilities**, **sportsbook puck lines**, and **expected value (EV)** — same blueprint as NBA Edge.

You and your friend just open the link. No Colab. No manual refresh every hour.

## How to use it

1. Open the GitHub Pages URL for this repo
2. Read the **ATS** board (primary) and the **Moneyline** bonus tab under ROI

The model shows **likelihoods**, not guaranteed covers.  
**ATS EV** = cover_prob × decimal odds − 1 (best available US **puck line**).  
**Moneyline** is logged separately as a bonus book — never mixed into ATS ROI.

Each hourly run auto-logs +EV ATS (and +EV ML) topsides into `docs/picks.json`, grades them when games finish, and updates each book’s equity curve.

## What runs in the background

Every hour from **8:00 AM to 11:00 PM Eastern**:

1. Update the games database (BallDontLie NHL API / NHL web fallback)
2. Train/score Model B (win prob → puck-line cover)
3. Pull live puck lines + moneylines (The Odds API `icehockey_nhl`)
4. Publish `docs/ev_board.json` + `docs/picks.json`

Overnight hours are skipped on purpose.

## One-time setup

### 1. Put this on GitHub

Create a repo, push this project, and invite your friend as a collaborator if you want.

### 2. Add API keys (Secrets)

Repo → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

| Secret name | Where to get it |
|-------------|-----------------|
| `BALLDONTLIE_API_KEY` | Optional for NHL — same key as NBA Edge. If NHL endpoints 401, we use the public NHL web API automatically. |
| `ODDS_API_KEY` | https://dash.the-odds-api.com/ (spreads + moneylines) |

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

- Primary book is **NHL ATS / puck line**; moneyline is a **bonus** ledger (Model B Elo + rolling margins).
- The research Colab (`NHL_Edge.ipynb`) is the longer-term feature lab; this repo is the live board.

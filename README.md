# Supply Chain Dashboard

Interactive Dash app for NJ Transit FIFA 2026 vendor sustainability scoring and procurement simulation.

## Run locally

```bash
pip install -r requirements.txt
python dashboard.py
```

Open `http://127.0.0.1:8050`.

## Deploy free on Render

This repo already includes `render.yaml` and `Procfile`.

1. Push this project to GitHub.
2. Create a Render account and connect your GitHub repo.
3. Click **New +** -> **Blueprint**.
4. Select this repository and deploy.
5. Render will create `supply-chain-dashboard` on the free plan and give you a live URL.

Notes:
- Free services spin down after inactivity and can take up to about a minute to wake.
- For this app, Render runs `gunicorn dashboard:server`.

## GitHub Pages note

GitHub Pages (`github.io`) is static hosting only, so it cannot run this Python Dash backend directly.

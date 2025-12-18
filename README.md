# YouTube Downloader (Flask + yt-dlp)

This is a Flask web app that downloads YouTube videos using `yt-dlp`.

## Can it “run on GitHub”?

GitHub Pages only hosts **static** sites (HTML/CSS/JS). It cannot run a Python/Flask backend like this app.

What you *can* do:

- Put the code on GitHub
- Deploy it to a free hosting platform that supports web servers (Render/Railway/Fly.io/etc.)

## Deploy (recommended: Render + GitHub)

1. Create a GitHub repo and push this folder:

```bash
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/<YOUR_USER>/<YOUR_REPO>.git
git push -u origin main
```

2. Go to Render → **New** → **Web Service** → **Build and deploy from a Git repository**.
3. Choose your repo.
4. For environment, pick **Docker** (Render will use `Dockerfile`).
5. Deploy. Render will give you a public URL like `https://your-service.onrender.com`.

Notes:
- Files in `downloads/` are temporary (most free hosts use ephemeral storage).
- Audio-only downloads use FFmpeg (installed in `Dockerfile`).

## Run locally

```bash
pip install -r requirements.txt
python app.py
```

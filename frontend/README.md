# EliteMinus — listener app (deploy this folder to Vercel)

Plain static HTML/CSS/JS. No build step, no framework, no `npm install`.

## Before you deploy

Open [`js/config.js`](js/config.js) and set `API_BASE` to your PythonAnywhere URL:

```js
API_BASE: "https://YOURUSERNAME.pythonanywhere.com"
```

No trailing slash. That's the only edit this folder needs.

## Deploy

```bash
npm i -g vercel
cd frontend
vercel --prod
```

When Vercel asks for settings: **no framework**, root directory `./`, no build
command, output directory `./`.

Or import the repo at [vercel.com/new](https://vercel.com/new) and set the
**Root Directory** to `frontend`.

## After deploying

Add your Vercel URL to the backend's `CORS_ORIGINS` and `FRONTEND_URL`, then
reload the PythonAnywhere web app. Without that the browser blocks every API
call.

## Files

| File | What it is |
|------|-----------|
| `index.html` | the player — sidebar, views, queue panel, transport bar |
| `login.html` / `register.html` / `verify.html` / `forgot.html` | account flow |
| `js/config.js` | **the one file you edit** — API base URL |
| `js/api.js` | fetch wrapper, Bearer-token storage, formatting helpers |
| `js/auth.js` | login / sign-up / OTP / forgot-password controllers |
| `js/components.js` | HTML render functions |
| `js/queue.js` | the playback queue (mirrors the server) |
| `js/player.js` | audio engine — picks Spotify or `<audio>` per track |
| `js/spotify.js` | Web Playback SDK + account linking |
| `js/app.js` | router and event wiring |
| `css/styles.css` | scrollbars, sliders, animations |
| `vercel.json` | static hosting config |

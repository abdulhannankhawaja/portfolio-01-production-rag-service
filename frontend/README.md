# Browser frontend

This React/Vite frontend is the browser client for the FastAPI service. Its
source lives in `src/`; production output is generated under `../app/static/`
and served by the Python app. Edit the source, not generated bundles.

## Build and lint

From this directory:

```bash
npm ci
npm run lint
npm run build
```

Run `npm run build` after changing the frontend so FastAPI serves the updated
assets. The build output directory is configured in `vite.config.js`.

## Run with the API

The supported local workflow is to build the frontend and then start FastAPI
from the repository root:

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open <http://127.0.0.1:8000/>. The frontend calls API routes at the same origin
and sends the current tab's bearer token for protected endpoints.

The Vite development server (`npm run dev`) does not currently configure an
API proxy. Use the built frontend through FastAPI for an end-to-end local
session, or configure a development proxy before using Vite's server.

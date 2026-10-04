# Future deployment: two Vercel projects

**Project owner:** Krishkumar | **Roll No:** 2401CS83 | **Institution:** IIT Patna

**GitHub repository:** https://github.com/Krish290107/agrisense

This is preparation for **Day 14**. No Vercel deployment is required for Day 1. Recheck the linked official documentation when deploying; platform settings may change. Guidance checked on October 3, 2026.

Connect the same GitHub repository to two Vercel projects, selecting a different Root Directory for each. Vercel supports this [monorepo setup](https://vercel.com/docs/monorepos).

| Setting | Backend project | Frontend project |
| --- | --- | --- |
| Suggested project name | `agrisense-api` | `agrisense-web` |
| Root Directory | `backend` | `frontend` |
| Framework | FastAPI | Next.js |
| Runtime | Python 3.13 | Node.js 24.x |
| Dependencies | `requirements.txt` | `package-lock.json` with `npm ci` |
| Build | FastAPI preset defaults | `npm run build` |
| Environment variable | `ALLOWED_ORIGINS` | `NEXT_PUBLIC_API_BASE_URL` |

The names are suggestions; your final URLs may differ. Use the actual URLs assigned to your projects throughout these steps.

## 1. Deploy the backend

1. Push the verified project using [GITHUB_SETUP.md](GITHUB_SETUP.md).
2. In the Vercel dashboard, add a project and import that repository.
3. Set **Root Directory** to `backend` and confirm the FastAPI framework preset.
4. Keep the preset's build and output settings. The committed `app.py` exports the `app` instance Vercel loads; `requirements.txt` lists its dependencies. Do not add a local `uvicorn --reload` start command. See [FastAPI deployment](https://vercel.com/docs/frameworks/backend/fastapi).
5. Keep `backend/.python-version` set to `3.13`; this file is at the backend project's root. Vercel supports this version-selection file and Python 3.13. See [the Python runtime](https://vercel.com/docs/functions/runtimes/python).
6. Deploy and copy the backend's stable production HTTPS address, such as `https://YOUR-API.vercel.app`.
7. Open that address with `/health` appended. It should return `{"status":"ok","service":"agrisense-api"}`. Also check `/docs`.

The initial backend can use its default origins until the real frontend URL is known. Directly opening `/health` does not require frontend CORS permission.

## 2. Deploy the frontend

1. Add another Vercel project and import the same repository.
2. Set **Root Directory** to `frontend` and select the Next.js framework preset.
3. Select Node.js **24.x**, matching `frontend/package.json`. See [supported Node.js versions](https://vercel.com/docs/functions/runtimes/node-js/node-js-versions).
4. Use `npm ci` as the install command and `npm run build` as the build command. Keep the Next.js output defaults.
5. Add `NEXT_PUBLIC_API_BASE_URL` for the **Production** environment with the actual backend HTTPS address, without `/health`. For example: `https://YOUR-API.vercel.app`.
6. Deploy and copy the frontend's stable production HTTPS address.

`NEXT_PUBLIC_API_BASE_URL` is public and embedded into the browser bundle. After changing it, rebuild/redeploy the frontend. Never use `localhost` or `127.0.0.1` for the deployed browser's API address: those refer to each visitor's own computer. See [Next.js public environment variables](https://nextjs.org/docs/app/guides/environment-variables).

## 3. Connect the production origins

In the **backend** project's environment settings, set `ALLOWED_ORIGINS` for **Production** to the exact frontend origin, for example:

```text
https://YOUR-WEB.vercel.app
```

For more than one intentional frontend origin, use a comma-separated list. Include the `https://` scheme and hostname, without a path or trailing slash. Add a custom domain explicitly if you later use one. Redeploy the backend after saving.

Vercel environment-variable changes affect new deployments, so changing settings alone does not update an existing deployment. See [Vercel environment variables](https://vercel.com/docs/environment-variables).

## 4. Verify the deployed connection

Open the production frontend, confirm the connection indicator succeeds, and use the browser Network panel to confirm a successful request to the HTTPS backend's `/health`. Check the response and CORS header. If the backend response is instead a deployment-protection login page, resolve access for the intended public API before testing the connection again.

For **Preview** deployments, set environment variables for Preview separately. Add each preview frontend origin you intentionally test to the backend's exact origin list, then redeploy that backend. Preview hostnames can change; do not use `*` or treat CORS as authentication.

The local `.env` files stay ignored by Git. Enter hosted settings in Vercel; do not upload local environments or dependencies. Future datasets, training jobs, model files, and database persistence need their own deployment design when those features are implemented.

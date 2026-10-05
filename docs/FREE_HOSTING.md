# Free Render deployment

Deployment configuration is prepared; a successful Render build and live acceptance test are still required.

1. Sign in to Render and connect GitHub access to **only** `Klauscreates/lunar-south-pole-explorer`.
2. Create a Blueprint from this repository's `main` branch and root `render.yaml`.
3. Confirm the single service has **Free / $0** pricing. Do not select a paid workspace, instance or disk.
4. Deploy, then use the service's assigned HTTPS `onrender.com` URL. Never guess the assigned hostname.
5. Verify `/api/terrain/health`, the Moon, all five locations, comparison, timelines and orbital view on that URL.

The Docker image includes the read-only terrain grids and checksummed study snapshot. The build runs the existing export integrity checks. Python stays on loopback; Next.js listens on Render's `PORT` and proxies terrain requests. No paid database, persistent disk, runtime science downloads or application secrets are needed. The container runs as a non-root user. Automatic deploys are disabled to avoid unexpected rebuilds; deploy new commits manually.

The default local launcher remains loopback-only. `PLANNER_HOST=0.0.0.0` is set only in the container. `requirements-serve.txt` pins the two terrain-serving dependencies; use `pyproject.toml` for scientific regeneration and testing.

Free services sleep after 15 minutes idle and can take about a minute to wake. Monthly compute, bandwidth and build limits apply. Do not add a payment method or upgrade to resolve a limit without approval. This is a demonstration host, not an always-on mission-critical service. Verify memory consumption under real traffic before claiming the 512 MB tier is sufficient.

Local container check, when Docker is available:

```sh
docker build -t lunar-explorer .
docker run --rm --memory=512m -p 10000:10000 lunar-explorer
```

Then open `http://127.0.0.1:10000` and run the acceptance script with `APP_URL` set to that address. Scientific results and data coverage are unchanged by hosting.

References: [Render free services](https://render.com/docs/free), [Blueprint specification](https://render.com/docs/blueprint-spec).

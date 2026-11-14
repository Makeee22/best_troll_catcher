# Deploy to the Hostinger VPS

Live at **https://swarm.srv2159299.hstgr.cloud** (VPS `srv2159299.hstgr.cloud`, Ubuntu, Docker).

Two containers from the root `docker-compose.yml`:
- `web`: nginx with the page, and a proxy for `/api/` and `/health`
- `api`: the backend's API (`backend/swarm`, unchanged) plus the upload endpoint of `frontend/api/app.py`. Reachable only from `web`.

The VPS already runs **Traefik** (Hostinger's Docker setup in `/docker/traefik`). It owns ports 80 and 443 and routes each subdomain of `srv2159299.hstgr.cloud` to a container by its labels, with Let's Encrypt certificates and http → https redirect. `deploy/docker-compose.hostinger.yml` gives `web` those labels and drops its port 80, so **always pass both `-f` files on this server.** Other projects on the VPS live in `/docker/<name>`; leave them alone.

## First time

```bash
ssh root@srv2159299.hstgr.cloud
cd /docker
git clone -b main https://github.com/Makeee22/best_troll_catcher.git spot-the-swarm   # makeee22/frontend until it is merged
cd spot-the-swarm
docker compose -p spot-the-swarm -f docker-compose.yml -f deploy/docker-compose.hostinger.yml up -d --build
curl -s https://swarm.srv2159299.hstgr.cloud/health      # {"status":"ok"}
```

The certificate is fetched on the first request; give it a few seconds. Then open the page once from a phone on mobile data.

## Update (plan branch B5: the SSH one-liner)

```bash
ssh root@srv2159299.hstgr.cloud "cd /docker/spot-the-swarm && git pull && docker compose -p spot-the-swarm -f docker-compose.yml -f deploy/docker-compose.hostinger.yml up -d --build"
```

An update restarts `api`, so the page goes back to the synthetic sample (uploads live in memory only).

## Use the backend on its own

Once the backend has its own upload endpoint, or to serve one fixed result, add a third file:

```bash
docker compose -p spot-the-swarm -f docker-compose.yml -f deploy/docker-compose.hostinger.yml -f deploy/docker-compose.backend.yml up -d --build
```

**Never put the Cresci 2017 data on the server:** it is research-only and holds real people's tweets.

## When something is wrong

```bash
cd /docker/spot-the-swarm
docker compose -p spot-the-swarm ps
docker compose -p spot-the-swarm logs --tail=50 api     # a bad RESULT_FILE / COMMENTS_FILE stops api with one message
docker compose -p spot-the-swarm logs --tail=50 web
docker logs --tail=50 traefik-traefik-1                 # routing or certificate problems
```

- 404 from Traefik: the `web` container is not running or lost its labels (was it started without the hostinger file?).
- Upload limits: 20 MB for both CSV files together (`MAX_BYTES` in `frontend/api/app.py`) and 100 MB for a saved Reddit page (`MAX_PAGE_BYTES` in `frontend/api/jobs.py`, `MAX_PAGE_BYTES` in `frontend/site/app.js`). `client_max_body_size` in `frontend/nginx.conf` (101m) must stay above the larger one.
- One result in memory, shared by every visitor: an upload replaces it for everybody until the next upload or restart.

## Anywhere else

On a machine without Traefik, `docker compose up -d --build` alone serves the page on port 80.

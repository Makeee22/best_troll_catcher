# Deploy to the Hostinger VPS

Ubuntu with Docker. Two containers from the root `docker-compose.yml`: `web` (nginx on port 80: the page, and a proxy for `/api/` and `/health`) and `api` (port 8000, reachable only from `web`).

Not tested on the VPS yet: these steps were written without Docker at hand.

## First time

```bash
ssh root@<server-ip>
docker --version && docker compose version     # both must answer
git clone https://github.com/Makeee22/best_troll_catcher.git
cd best_troll_catcher
git checkout makeee22/frontend                 # skip once the branch is merged to main
docker compose up -d --build
ufw allow 80/tcp                               # only matters if ufw is on: `ufw status`
curl http://localhost/health                   # {"status":"ok"}
```

Then open `http://<server-ip>/` in a browser, and once from a phone on mobile data. If it answers on the server but not from outside, check the firewall in the Hostinger panel (hPanel → VPS → Firewall) and allow TCP 80.

## Update (plan branch B5: the SSH one-liner)

```bash
ssh root@<server-ip> "cd best_troll_catcher && git pull && docker compose up -d --build"
```

## Switch `api` from the mock to the real backend

```bash
docker compose -f docker-compose.yml -f deploy/docker-compose.backend.yml up -d --build
```

Use the same two `-f` flags in the update command from then on. The real backend has no `POST /api/analyze` yet, so until it does the page shows the backend's own data and uploads give a clear message. Back to the mock: `docker compose up -d --build`.

## When something is wrong

```bash
docker compose ps
docker compose logs --tail=50 api
docker compose logs --tail=50 web
docker compose down && docker compose up -d --build
```

- Port 80 taken: `ss -ltnp | grep :80` shows by what (often a preinstalled apache2 or nginx: `systemctl disable --now apache2`).
- The upload limit is 20 MB in two places that must agree: `MAX_BYTES` in `frontend/mock/app.py` and `client_max_body_size` in `frontend/nginx.conf`.
- The mock keeps the uploaded data in memory: a restart returns to the synthetic sample.

## Later, optional: HTTPS

Point the free domain's A record at the server, then either put Caddy in front (it fetches certificates by itself) or add certbot to the nginx container, and open port 443. Not needed for the demo link to work.

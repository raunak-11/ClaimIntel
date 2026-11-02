# Deploying ClaimIntel on EC2

Everything here assumes the bundle `ClaimIntel-EC2-<date>.zip`, which is this
repo with `node_modules`, `.git` and build caches stripped and the claim queue
reset to a fresh install. `.env` **is inside the bundle**, so the zip carries
live API keys: treat it as a secret, do not put it in S3 public, Slack, email
or a GitHub release.

## 1. The instance

| | |
|---|---|
| Type | **t3.medium** or larger (2 vCPU, 4 GB RAM) |
| Disk | **30 GB** gp3 |
| AMI | Ubuntu 22.04/24.04 or Amazon Linux 2023 |
| Inbound | 22 (your IP), **3000** (the app), 8001 only if you want to curl the API directly |

Do not try this on a t2/t3.micro. The backend image installs CPU torch and
bakes in two ONNX models at build time (ChromaDB's `all-MiniLM-L6-v2`, ~79 MB,
and the image-forensics classifier, ~90 MB), which is a multi-GB image and a
long first build. Baking them in is deliberate: a container that downloads them
on first use blocks Agent 1 for 5 to 15 minutes, and it would do it on the one
run anybody is watching. 1 GB of RAM will have the build killed by the OOM
reaper, usually while resolving torch, and the error will not say so.

## 2. Docker

Ubuntu:

```bash
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-v2 unzip
sudo usermod -aG docker $USER && newgrp docker
```

Amazon Linux 2023:

```bash
sudo dnf install -y docker unzip
sudo systemctl enable --now docker
sudo usermod -aG docker $USER && newgrp docker
sudo dnf install -y docker-compose-plugin   # or the compose v2 binary
```

## 3. Upload and start

From your laptop:

```bash
scp -i key.pem ClaimIntel-EC2-<date>.zip ubuntu@<ec2-ip>:~/
```

On the instance:

```bash
unzip -q ClaimIntel-EC2-<date>.zip && cd ClaimIntel
docker compose up --build -d      # first build takes a while: torch + 2 ONNX models
docker compose logs -f backend    # watch until the healthcheck passes
```

Open **http://\<ec2-ip\>:3000**.

The browser only ever talks to port 3000. nginx proxies `/api/` and `/uploads/`
to the backend inside the Docker network (`frontend/nginx.conf`), so the app is
same-origin and no CORS setting is involved. `ALLOWED_ORIGINS` matters only if
something calls `:8001` directly; it now reads from `.env` if you set it.

## 4. Verify before demoing

```bash
curl http://localhost:8001/api/health
curl http://localhost:8001/api/health/models     # every configured model, per provider
docker compose exec backend python -c "import config; print(len(config.SERPER_API_KEYS), len(config.TAVILY_API_KEYS))"
```

`/api/health/models` is the one that matters. Two Groq models were retired
mid-project and both times the first symptom was a live investigation dying
halfway. Run it once before the demo, not during.

On search keys: both providers are free-tier and quota-capped, and one
investigation spends 20 to 50 searches. `SERPER_API_KEY` / `TAVILY_API_KEY`
each take a chain (`_2` ... `_9`) and `price_lookup` rotates on a quota or auth
refusal, printing a line when it does:

```
[pricing] tavily key ...Qx2T spent (HTTP 432)
```

Watch for that in `docker compose logs backend`. When a chain is fully spent
the pipeline does not fail, it abstains: parts come back unpriced,
`pricing_coverage` drops under the floor and the fair-value bands decline to
reach a verdict. Quiet, not loud, which is why the log line exists.

Note that `google.serper.dev` is TLS-blocked on some corporate networks (the
handshake is refused before the key is ever sent). If Serper worked on EC2 but
not on your laptop, that is why.

## 5. Refresh the demo cases

Case fraud profiles depend on how many days ago the incident was (FC-05 late
reporting), so the fixtures are generated against today's date. Re-run this the
morning of the demo:

```bash
docker compose run --rm -v "$(pwd)/dev:/app/dev" backend \
    python /app/dev/scripts/generate_test_cases.py
```

`dev/` is not in the image (it is excluded by `.dockerignore`), hence the mount.
It writes into `data/`, which is bind-mounted, so the running backend picks the
new manifest up on its own: it is mtime-keyed, no restart needed.

Damage photos are gitignored. If the bundle was built from a clone rather than
a working tree, the quick-fill buttons will attach the PDFs and name the photos
they could not find.

## 6. Operating notes

```bash
docker compose restart backend       # after editing .env
docker compose down                  # stop; ./data persists on the host
docker compose up -d                 # start again, no rebuild
python dev/scripts/reset_claims.py --yes    # empty the queue between demo runs
```

`./data` is bind-mounted, so claims, uploads, results, reports and the
vectorstore all live on the instance disk and survive `docker compose down`.
They do not survive terminating the instance. If the demo produced anything
worth keeping, `scp` the `data/` directory off before you terminate.

`DEMO_MODE` defaults to true, which is what puts the quick-fill buttons on the
New Claim page. Set it false in anything resembling a real deployment.

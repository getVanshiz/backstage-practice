# Backstage Local Setup — Step by Step

A local Backstage instance backed by Postgres, integrated with GitLab.
This is **Phase 1** of your internship project.

---

## Directory layout

```
backstage-local/
├── docker-compose.yml             ← Postgres + Backstage containers
├── Dockerfile                     ← Builds the Backstage image
├── app-config.production.yaml     ← Prod overrides (Postgres, GitLab)
├── catalog-info.yaml              ← Template to drop in your GitLab repos
├── gitlab_catalog_scanner.py      ← Phase 2: finds repos missing YAML
├── .env                           ← YOUR SECRETS — never commit this
└── backstage-app/                 ← Created by `npx @backstage/create-app`
    ├── app-config.yaml            ← Default config (SQLite, guest auth)
    └── ...
```

---

## Prerequisites

| Tool | Version |
|------|---------|
| Node.js | 20.x |
| Yarn | 1.x (`npm i -g yarn`) |
| Docker + Docker Compose | any recent |
| Python | 3.9+ (for scanner script only) |

---

## Step 1 — Scaffold the Backstage app

```bash
# Run this ONCE from inside backstage-local/
npx @backstage/create-app@latest
# When prompted:
#   Name: backstage-app        ← must match docker-compose.yml context path
#   Database: PostgreSQL
```

This creates `backstage-local/backstage-app/`.

---

## Step 2 — Create your .env file

```bash
cat > .env <<'EOF'
GITLAB_TOKEN=glpat-xxxxxxxxxxxxxxxxxxxx   # GitLab PAT: scopes read_api, read_repository
POSTGRES_USER=backstage
POSTGRES_PASSWORD=backstage
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
APP_BASE_URL=http://localhost:7007
BACKEND_BASE_URL=http://localhost:7007
EOF
```

> **Never commit .env** — add it to .gitignore

---

## Step 3 — Edit app-config.production.yaml

Open `app-config.production.yaml` and update:

```yaml
integrations:
  gitlab:
    - host: gitlab.mycompany.com    # ← your company's GitLab host
      token: ${GITLAB_TOKEN}

catalog:
  locations:
    - type: url
      target: https://gitlab.mycompany.com/YOUR_GROUP/YOUR_REPO/-/blob/main/catalog-info.yaml
```

---

## Step 4 — Build the Backstage backend

```bash
cd backstage-app
yarn install
yarn tsc
yarn build:backend
cd ..
```

This produces `backstage-app/packages/backend/dist/`.
**You must re-run this whenever you change backend code or install plugins.**

---

## Step 5 — Start everything

```bash
docker compose --env-file .env up --build
```

- Postgres starts first (health-checked)
- Backstage starts, connects to Postgres, runs migrations automatically
- Open **http://localhost:7007**

> First startup is slow (~30–60s). Subsequent starts are faster.

---

## Step 6 — Register your first service

1. Copy `catalog-info.yaml` into the root of a GitLab repo you own
2. Edit the fields (name, owner, description, GitLab slug)
3. Commit and push to `main`
4. Backstage re-polls every 60 seconds and picks it up automatically

Or register it immediately via the UI:
**Catalog → Register Existing Component → paste the raw YAML URL**

---

## Step 7 — Verify in the UI

Go to http://localhost:7007/catalog — you should see your component card.
Click it to see the overview, relations, and metadata.

---

## Phase 2 — Auto-ingestion for existing repos

Once the manual flow works, use the scanner:

```bash
pip install python-gitlab
export GITLAB_TOKEN=glpat-xxxx
export GITLAB_HOST=gitlab.mycompany.com
export GITLAB_GROUP=your-top-group

# Just report which repos are missing catalog-info.yaml
python gitlab_catalog_scanner.py

# Auto-open MRs for missing repos
CREATE_MRS=true python gitlab_catalog_scanner.py
```

Then enable GitLab Discovery in `app-config.production.yaml` so Backstage
auto-ingests every repo that merges those MRs:

```yaml
# Install the plugin first:
# cd backstage-app && yarn add @backstage/plugin-catalog-backend-module-gitlab

catalog:
  locations:
    - type: gitlab-discovery
      target: https://gitlab.mycompany.com/YOUR_GROUP/*/catalog-info.yaml
```

---

## Common issues

| Symptom | Fix |
|---------|-----|
| `ECONNREFUSED` on startup | Postgres not ready yet — wait 10s and retry |
| `Missing required config: integrations.gitlab.token` | Check `.env` has `GITLAB_TOKEN` and you ran `--env-file .env` |
| Entity not showing up in catalog | Check the URL in `locations` is the raw YAML URL, not the GitLab web view |
| `yarn build:backend` fails | Make sure you ran `yarn install` and `yarn tsc` first |
| Port 5432 already in use | Another Postgres is running locally — change the host port in docker-compose |

---

## Architecture — what each file does

```
GitLab repo (catalog-info.yaml)
        │
        │  Backstage polls every 60s
        ▼
  Backstage Backend
  (catalog processor)
        │
        │  Stores parsed entities
        ▼
    Postgres DB
  (backstage schema)
        │
        │  API queries
        ▼
  Backstage Frontend
  http://localhost:7007
```

Later you'll add:
- **StarArc/SA inventory** → custom ingestion plugin (reads from SA API, pushes Resource entities)
- **Voyager** → change event hook → update entity annotations
- **Scorecards** → custom Backstage plugin that queries Jira + Voyager + SA to compute scores

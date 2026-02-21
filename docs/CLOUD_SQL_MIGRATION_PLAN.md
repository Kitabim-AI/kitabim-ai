# Minimalistic Cloud SQL Migration Plan (Cost-Optimized)

**Goal**: Migrate Kitabim AI's PostgreSQL to a Cloud SQL instance optimized for the absolute lowest reasonable cost (~$25/month). This plan cuts out High Availability (HA) and automated backups to focus entirely on simplicity and budget, while using a basic `db-g1-small` and SSD to ensure pgvector RAG perform adequately.

## Phase 1: Provision Minimal Infrastructure

We use a shared-core `db-g1-small` instance with minimum Zonal SSD storage.

```bash
# Configuration
PROJECT_ID="kitabim-ai-prod"
INSTANCE_NAME="kitabim-db-prod"
REGION="us-central1"

# 1. Create minimal instance (~$15/month compute + $1.70/month SSD 10GB = ~$17/mo total)
gcloud sql instances create $INSTANCE_NAME \
  --project=$PROJECT_ID \
  --database-version=POSTGRES_15 \
  --tier=db-g1-small \
  --region=$REGION \
  --availability-type=ZONAL \
  --storage-type=SSD \
  --storage-size=10GB \
  --no-backup \
  --no-assign-ip
```

# 2. Create DB and User
gcloud sql databases create kitabim_ai --instance=$INSTANCE_NAME
APP_PASSWORD=$(openssl rand -base64 24)
echo "SAVE THIS DB PASSWORD: $APP_PASSWORD"
gcloud sql users create kitabim-app-user --instance=$INSTANCE_NAME --password=$APP_PASSWORD

# 3. Allow K8s Service Account to Access DB
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:ai-kitabim-prod-sa@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/cloudsql.client"
```

## Phase 2: Simple Schema & Data Migration

Instead of separate schema scripts and validations, we'll do a direct full dump and restore.

```bash
# 1. Start Cloud SQL Proxy locally
cloud-sql-proxy ${PROJECT_ID}:${REGION}:${INSTANCE_NAME} --port 5433 &
PROXY_PID=$!

# 2. Dump local database
pg_dump -U omarjan -d kitabim_ai -F c -f kitabim_dump.sql

# 3. Create required extensions on Cloud SQL as postgres default admin
# Get your Postgres user password from GCP Console if you don't have it, or reset it.
PGPASSWORD='<POSTGRES_ADMIN_PASSWORD>' psql -h localhost -p 5433 -U postgres -d kitabim_ai -c 'CREATE EXTENSION IF NOT EXISTS "uuid-ossp"; CREATE EXTENSION IF NOT EXISTS "vector";'

# 4. Restore dump directly to Cloud SQL using the app user
export PGPASSWORD=$APP_PASSWORD
pg_restore -h localhost -p 5433 -U kitabim-app-user -d kitabim_ai -O -x --clean kitabim_dump.sql

# 5. Stop proxy
kill $PROXY_PID
```

## Phase 3: Application Cutover

```bash
# 1. Store Credentials in Kubernetes
kubectl create secret generic cloudsql-db-credentials \
  -n kitabim \
  --from-literal=username=kitabim-app-user \
  --from-literal=password=$APP_PASSWORD \
  --from-literal=database=kitabim_ai \
  --from-literal=connection_name="${PROJECT_ID}:${REGION}:${INSTANCE_NAME}"
```

### 2. Update K8s Manifests (`k8s/local/backend.yaml` and `k8s/local/worker.yaml`)
Update your deployments to point `DATABASE_URL` to `localhost`, and add the Cloud SQL Proxy sidecar to handle the secure tunnel.

```yaml
      containers:
        # --- Update Main Container Env ---
        - name: backend  # or worker
          env:
            - name: DATABASE_URL
              value: "postgresql://$(CLOUDSQL_USER):$(CLOUDSQL_PASSWORD)@localhost:5432/$(CLOUDSQL_DATABASE)"
            - name: CLOUDSQL_USER
              valueFrom: { secretKeyRef: { name: cloudsql-db-credentials, key: username } }
            - name: CLOUDSQL_PASSWORD
              valueFrom: { secretKeyRef: { name: cloudsql-db-credentials, key: password } }
            - name: CLOUDSQL_DATABASE
              valueFrom: { secretKeyRef: { name: cloudsql-db-credentials, key: database } }
            - name: GOOGLE_APPLICATION_CREDENTIALS
              value: /etc/gcs/key.json

        # --- Add Sidecar Container ---
        - name: cloud-sql-proxy
          image: gcr.io/cloud-sql-connectors/cloud-sql-proxy:2.13.0
          args:
            - "--port=5432"
            - "--credentials-file=/etc/gcs/key.json"
            - "$(CLOUD_SQL_CONNECTION_NAME)"
          env:
            - name: CLOUD_SQL_CONNECTION_NAME
              valueFrom: { secretKeyRef: { name: cloudsql-db-credentials, key: connection_name } }
          volumeMounts:
            - name: gcs-key
              mountPath: /etc/gcs
              readOnly: true
```

### 3. Deploy
```bash
# Apply deployments and restart
kubectl apply -f k8s/local/backend.yaml
kubectl apply -f k8s/local/worker.yaml
kubectl rollout restart deployment/backend deployment/worker -n kitabim
```

## Cost Comparison

| Feature | Original Plan (~$150/mo) | Minimal Plan (~$17/mo) |
| :--- | :--- | :--- |
| **Instance Tier** | 2 vCPU, 7.5GB RAM | `db-g1-small` (shared core, 1.7GB RAM) |
| **Storage** | 50GB SSD | 10GB SSD |
| **Availability** | Regional (HA Failover) | Zonal (Single Zone) |
| **Backups** | Automated & Kept 7 Days | Disabled (`--no-backup`) |
| **Migration** | Zero downtime | ~5 min downtime |

> **Warning:** Using `db-g1-small` disables automated backups. While it handles basic pgvector queries better than an f1-micro, it still uses a shared CPU core. If you notice RAG queries failing, timing out, or taking too long, you can upgrade this instance to `db-custom-1-3840` (~$50/mo+ storage) with one click in the Google Cloud Console. Since automated backups are off by default on this tier, if you use this database for important user data, it is highly recommended to run manual `pg_dump` backups occasionally.

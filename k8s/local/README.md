# Local Kubernetes Deployment

This directory contains Kubernetes manifests for deploying Kitabim.AI locally using Kubernetes (Docker Desktop, minikube, or kind).

## Prerequisites

1. **Local Kubernetes cluster** (choose one):
   - Docker Desktop with Kubernetes enabled
   - minikube: `minikube start`
   - kind: `kind create cluster`

2. **kubectl** installed and configured

3. **Local PostgreSQL** running with the migrated data
   - Host: `localhost:5432`
   - Database: `kitabim_ai`
   - Accessible from Kubernetes using `host.docker.internal`

## Quick Start

### 1. Configure Secrets

Edit `k8s/local/secrets.yaml` and add your API keys:

```yaml
stringData:
  GEMINI_API_KEY: "your-actual-gemini-api-key"
  JWT_SECRET_KEY: "your-strong-random-secret-at-least-32-characters"
```

### 2. Build Docker Images

```bash
# Build backend image
docker build -f Dockerfile.backend -t kitabim-backend:local .

# Build worker image
docker build -f Dockerfile.worker -t kitabim-worker:local .

# Build frontend image (if you have a frontend Dockerfile)
# docker build -f apps/frontend/Dockerfile -t kitabim-frontend:local apps/frontend
```

### 3. Deploy to Kubernetes

```bash
# Apply all manifests
kubectl apply -f k8s/local/

# Or apply individually in order:
kubectl apply -f k8s/local/secrets.yaml
kubectl apply -f k8s/local/configmap.yaml
kubectl apply -f k8s/local/redis.yaml
kubectl apply -f k8s/local/backend.yaml
kubectl apply -f k8s/local/worker.yaml
# kubectl apply -f k8s/local/frontend.yaml  # If you have frontend
```

### 4. Verify Deployment

```bash
# Check pod status
kubectl get pods

# Check services
kubectl get svc

# View logs
kubectl logs -f deployment/backend
kubectl logs -f deployment/worker
kubectl logs -f deployment/redis
```

### 5. Access the Application

The backend API is exposed on NodePort 30800:

```bash
# Get the cluster IP (for minikube)
minikube ip  # Example: 192.168.49.2

# Access the API
curl http://localhost:30800/health
# OR
curl http://$(minikube ip):30800/health
```

For Docker Desktop, access via:
- Backend API: http://localhost:30800
- Frontend: http://localhost:30080

## Configuration

### Database Connection

The application connects to your local PostgreSQL using `host.docker.internal`:

```yaml
DATABASE_URL: "postgresql://omarjan@host.docker.internal:5432/kitabim_ai"
```

This works for:
- ✓ Docker Desktop (built-in)
- ✓ minikube (may need `minikube ssh` and port forwarding)
- ✓ kind (may need host network configuration)

### Environment Variables

**Secrets** (`secrets.yaml`):
- `GEMINI_API_KEY` - Required for AI features
- `JWT_SECRET_KEY` - Required for authentication
- `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` - Optional OAuth

**ConfigMap** (`configmap.yaml`):
- Database, Redis, and service URLs
- Model configurations
- Processing limits
- RAG parameters

## Troubleshooting

### Pods not starting

```bash
# Check pod status
kubectl describe pod <pod-name>

# Check logs
kubectl logs <pod-name>
```

### Can't connect to PostgreSQL

For minikube, you may need to enable host access:

```bash
# Option 1: Use minikube tunnel
minikube tunnel

# Option 2: Port forward from host
kubectl port-forward svc/backend 8000:8000
```

For kind, add to cluster config:

```yaml
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
nodes:
- role: control-plane
  extraPortMappings:
  - containerPort: 30800
    hostPort: 30800
```

### Images not found

Make sure you're using the correct image pull policy:

```bash
# For minikube, load images into the cluster
minikube image load kitabim-backend:local
minikube image load kitabim-worker:local

# For kind
kind load docker-image kitabim-backend:local
kind load docker-image kitabim-worker:local
```

### Clean up

```bash
# Delete all resources
kubectl delete -f k8s/local/

# Or delete individually
kubectl delete deployment backend worker redis
kubectl delete svc backend redis
kubectl delete configmap kitabim-config
kubectl delete secret kitabim-secrets
```

## Production Deployment

For GCP deployment, see the GCP-specific manifests in `k8s/gcp/` (coming soon).

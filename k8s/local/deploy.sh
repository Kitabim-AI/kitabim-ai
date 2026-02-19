#!/bin/bash
# Local Kubernetes deployment script for Kitabim.AI

set -e

echo "🚀 Deploying Kitabim.AI to local Kubernetes..."

# Check if kubectl is available
if ! command -v kubectl &> /dev/null; then
    echo "❌ kubectl not found. Please install kubectl first."
    exit 1
fi

# Check if cluster is running
if ! kubectl cluster-info &> /dev/null; then
    echo "❌ Kubernetes cluster is not running."
    echo "Please start your cluster (Docker Desktop, minikube, or kind)."
    exit 1
fi

echo "✓ Kubernetes cluster is running"

# Detect cluster type
if kubectl config current-context | grep -q "minikube"; then
    CLUSTER_TYPE="minikube"
    echo "✓ Detected minikube cluster"
elif kubectl config current-context | grep -q "kind"; then
    CLUSTER_TYPE="kind"
    echo "✓ Detected kind cluster"
else
    CLUSTER_TYPE="docker-desktop"
    echo "✓ Detected Docker Desktop cluster"
fi

# Load .env file with overrides
if [ -f .env ]; then
    echo "📄 Processing .env file..."
    
    # Check for GEMINI_API_KEY in .env
    if ! grep -q "^GEMINI_API_KEY=" .env || [ -z "$(grep "^GEMINI_API_KEY=" .env | cut -d '=' -f2)" ]; then
        echo "⚠️  WARNING: GEMINI_API_KEY is missing or empty in .env"
        echo "   The application will fail to start without it."
        read -p "   Continue anyway? (y/N) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            echo "Please edit .env and add your GEMINI_API_KEY"
            exit 1
        fi
    fi

    # Create a temporary .env for Kubernetes with overridden values
    echo "# Kubernetes Environment Overrides" > .env.k8s
    
    # Copy all content first, commenting out keys we will override
    grep -v "^DATABASE_URL=" .env | \
    grep -v "^REDIS_URL=" | \
    grep -v "^DATA_DIR=" | \
    grep -v "^GOOGLE_REDIRECT_URI=" >> .env.k8s

    # Add Kubernetes-specific overrides
    echo "" >> .env.k8s
    echo "# Overrides for Container Environment" >> .env.k8s

    if [ "$CLUSTER_TYPE" = "minikube" ]; then
        # Minikube networking
        echo "DATABASE_URL=postgresql://postgres:postgres@host.minikube.internal:5432/kitabim_ai" >> .env.k8s
        echo "REDIS_URL=redis://redis:6379/0" >> .env.k8s
        echo "GOOGLE_REDIRECT_URI=http://$(minikube ip):30080/api/auth/google/callback" >> .env.k8s
    else
        # Docker Desktop / Kind networking
        echo "DATABASE_URL=postgresql://omarjan@host.docker.internal:5432/kitabim_ai" >> .env.k8s
        echo "REDIS_URL=redis://redis:6379/0" >> .env.k8s
        echo "GOOGLE_REDIRECT_URI=http://localhost:30080/api/auth/google/callback" >> .env.k8s
    fi
    
    # Common container paths
    echo "DATA_DIR=/app/data" >> .env.k8s

else
    echo "⚠️  WARNING: .env file not found."
    exit 1
fi

# Generate a unique tag for this deployment
DEPLOY_TAG=$(date +%s)
echo "🏷️  Using deployment tag: $DEPLOY_TAG"

# Build Docker images
echo ""
echo "📦 Building Docker images..."

docker build -f Dockerfile.backend -t kitabim-backend:$DEPLOY_TAG -t kitabim-backend:local . || {
    echo "❌ Failed to build backend image"
    exit 1
}
echo "✓ Built kitabim-backend:$DEPLOY_TAG"

docker build -f Dockerfile.worker -t kitabim-worker:$DEPLOY_TAG -t kitabim-worker:local . || {
    echo "❌ Failed to build worker image"
    exit 1
}
echo "✓ Built kitabim-worker:$DEPLOY_TAG"

docker build -t kitabim-frontend:$DEPLOY_TAG -t kitabim-frontend:local -f apps/frontend/Dockerfile . || {
    echo "❌ Failed to build frontend image"
    exit 1
}
echo "✓ Built kitabim-frontend:$DEPLOY_TAG"

# Load images into cluster if needed
if [ "$CLUSTER_TYPE" = "minikube" ]; then
    echo ""
    echo "📥 Loading images into minikube..."
    minikube image load kitabim-backend:$DEPLOY_TAG
    minikube image load kitabim-worker:$DEPLOY_TAG
    minikube image load kitabim-frontend:$DEPLOY_TAG
    echo "✓ Images loaded into minikube"
elif [ "$CLUSTER_TYPE" = "kind" ]; then
    echo ""
    echo "📥 Loading images into kind..."
    kind load docker-image kitabim-backend:$DEPLOY_TAG
    kind load docker-image kitabim-worker:$DEPLOY_TAG
    kind load docker-image kitabim-frontend:$DEPLOY_TAG
    echo "✓ Images loaded into kind"
fi

# Apply Kubernetes manifests (generating secrets/config from .env.k8s)
echo ""
echo "☸️  Applying Kubernetes manifests..."

# Create namespace if it doesn't exist
kubectl create namespace kitabim --dry-run=client -o yaml | kubectl apply -f -
echo "✓ Ensures namespace 'kitabim' exists"

# Create Secret from .env.k8s
kubectl create secret generic kitabim-secrets \
    -n kitabim \
    --from-env-file=.env.k8s \
    --dry-run=client -o yaml | kubectl apply -f -
echo "✓ Created/Updated kitabim-secrets from .env"

# Create ConfigMap from .env.k8s
kubectl create configmap kitabim-config \
    -n kitabim \
    --from-env-file=.env.k8s \
    --dry-run=client -o yaml | kubectl apply -f -
echo "✓ Created/Updated kitabim-config from .env"

# Create GCS key secret if file exists
if [ -f gcs-key.json ]; then
    kubectl create secret generic kitabim-gcs-key \
        -n kitabim \
        --from-file=key.json=gcs-key.json \
        --dry-run=client -o yaml | kubectl apply -f -
    echo "✓ Created/Updated kitabim-gcs-key from gcs-key.json"
fi

# Clean up temp file
rm .env.k8s

kubectl apply -f k8s/local/redis.yaml
echo "✓ Applied redis"

# Update images in manifests and apply
sed "s|image: kitabim-backend:local|image: kitabim-backend:$DEPLOY_TAG|g" k8s/local/backend.yaml | kubectl apply -f -
echo "✓ Applied backend"

sed "s|image: kitabim-worker:local|image: kitabim-worker:$DEPLOY_TAG|g" k8s/local/worker.yaml | kubectl apply -f -
echo "✓ Applied worker"

sed "s|image: kitabim-frontend:local|image: kitabim-frontend:$DEPLOY_TAG|g" k8s/local/frontend.yaml | kubectl apply -f -
echo "✓ Applied frontend"

# Wait for deployments to be ready
echo ""
echo "⏳ Waiting for deployments to be ready..."
kubectl wait -n kitabim --for=condition=available --timeout=120s deployment/redis
kubectl wait -n kitabim --for=condition=available --timeout=120s deployment/backend
kubectl wait -n kitabim --for=condition=available --timeout=120s deployment/worker
kubectl wait -n kitabim --for=condition=available --timeout=120s deployment/frontend

echo ""
echo "✅ Deployment complete!"
echo ""
echo "📊 Status:"
kubectl get pods -n kitabim
echo ""
kubectl get svc -n kitabim

echo ""
echo "🌐 Access the application:"
if [ "$CLUSTER_TYPE" = "minikube" ]; then
    MINIKUBE_IP=$(minikube ip)
    echo "   Frontend:    http://$MINIKUBE_IP:30080"
    echo "   Backend API: http://$MINIKUBE_IP:30800"
    echo "   Health check: curl http://$MINIKUBE_IP:30800/health"
else
    echo "   Frontend:    http://localhost:30080"
    echo "   Backend API: http://localhost:30800"
    echo "   Health check: curl http://localhost:30800/health"
fi

echo ""
echo "📝 Useful commands:"
echo "   kubectl get pods -n kitabim              # View pod status"
echo "   kubectl logs -f deployment/backend -n kitabim  # View backend logs"
echo "   kubectl logs -f deployment/worker -n kitabim   # View worker logs"
echo "   kubectl delete -f k8s/local/              # Delete all resources"

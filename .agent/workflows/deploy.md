---
description: How to deploy changes to Kubernetes
---

# Deploying to Kubernetes

When you make changes to the codebase, they must be deployed to Kubernetes to be visible. Do not rely on local `npm run dev` servers to verify the changes if you are acting on behalf of the user, as the user is testing via the deployed Kubernetes cluster.

## Deployment Steps

To deploy the changes to Kubernetes, you should use the provided wrapper script from the repository root:

// turbo
1. Rebuild and restart the necessary component:
```bash
./rebuild-and-restart.sh [component]
```

Where `[component]` is one of:
- `backend` - To rebuild and restart the backend API container
- `worker` - To rebuild and restart the background worker task container
- `frontend` - To rebuild and restart the frontend React container
- `all` - To rebuild and restart all components (default)

For example, to deploy a frontend UI change:
```bash
./rebuild-and-restart.sh frontend
```

2. Wait for the pod to successfully recycle and start running. The script will automatically trigger a `kubectl rollout restart` and then display the pod deployment status.

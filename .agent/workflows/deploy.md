---
description: How to deploy changes locally using Docker Compose
---

# Local Deployment (Redeploy)

When you make changes to the codebase, they must be rebuilt and restarted within the Docker Compose environment to be visible. Do not rely on local `npm run dev` or `uvicorn` processes to verify the final application state, as the Docker environment may have different configurations.

## Deployment Steps

To rebuild and restart specific services in the local Docker environment, use the provided script:

// turbo
1. Rebuild and restart the necessary component:
```bash
./deploy/local/rebuild-and-restart.sh [component]
```

Where `[component]` is one of:
- `backend` - To rebuild and restart the backend FastAPI container
- `worker` - To rebuild and restart the ARQ background worker container
- `frontend` - To rebuild and restart the frontend React container
- `all` - To rebuild and restart all components

For example, to deploy a frontend UI change:
```bash
./deploy/local/rebuild-and-restart.sh frontend
```

2. The script will:
- Rebuild the Docker image for that specific service.
- Re-create and restart the container using `docker compose up -d`.
- Display the status of the containers once finished.

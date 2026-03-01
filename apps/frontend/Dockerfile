# syntax=docker/dockerfile:1.4
# Stage 1: Build
FROM node:20-alpine AS build

WORKDIR /repo

# Copy workspace configuration and package locks
COPY package.json package-lock.json ./
COPY packages/shared/package.json ./packages/shared/
COPY apps/frontend/package.json apps/frontend/package-lock.json ./apps/frontend/

# Install dependencies with cache mount
RUN --mount=type=cache,target=/root/.npm \
  npm ci --workspace apps/frontend --workspace packages/shared --include=optional

# Architecture-specific rollup fix for Alpine (musl)
RUN --mount=type=cache,target=/root/.npm \
  ROLLUP_PKG=$(node -p "require('os').arch()==='arm64'?'@rollup/rollup-linux-arm64-musl':'@rollup/rollup-linux-x64-musl'") \
    && npm install --workspace apps/frontend --no-save "$ROLLUP_PKG"

# Copy source code
COPY packages/shared ./packages/shared
COPY apps/frontend ./apps/frontend

# Build the frontend
WORKDIR /repo/apps/frontend
RUN npm run build

# Stage 2: Production (Nginx)
FROM nginx:1.27-alpine

COPY apps/frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /repo/apps/frontend/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]

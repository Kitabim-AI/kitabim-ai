FROM node:20-bullseye-slim AS build

WORKDIR /repo

COPY . .

WORKDIR /repo/apps/frontend
RUN npm ci --include=optional
RUN ROLLUP_PKG=$(node -p "require('os').arch()==='arm64'?'@rollup/rollup-linux-arm64-gnu':'@rollup/rollup-linux-x64-gnu'") \
    && npm install --no-save "$ROLLUP_PKG"
RUN npm run build

FROM nginx:1.27-alpine
COPY apps/frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /repo/apps/frontend/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]

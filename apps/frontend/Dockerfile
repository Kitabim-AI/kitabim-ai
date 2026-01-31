FROM node:18-alpine AS build

WORKDIR /repo

COPY . .

WORKDIR /repo/apps/frontend
RUN npm ci
RUN npm run build

FROM nginx:1.27-alpine
COPY apps/frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /repo/apps/frontend/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]

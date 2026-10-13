FROM node:20-alpine AS build
WORKDIR /app

# install from the lockfile for a reproducible build
COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# VITE_API_BASE is inlined at build time. Leave it empty so the browser calls
# this same origin and nginx (below) proxies /api and /ws to the api service.
ARG VITE_API_BASE=""
ENV VITE_API_BASE=$VITE_API_BASE
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80

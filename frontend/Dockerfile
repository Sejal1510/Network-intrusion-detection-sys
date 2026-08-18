# syntax=docker/dockerfile:1

FROM node:22-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .

# Vite env vars are compiled into the bundle at build time (see
# src/api/client.ts), not read at container start -- so the backend URL
# the browser will call has to be known here, as a build ARG, not as a
# runtime environment variable on the nginx container.
ARG VITE_API_BASE_URL=http://localhost:8000
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
# *.template under /etc/nginx/templates/ is rendered via envsubst into
# /etc/nginx/conf.d/ (stripping the suffix) by the base image's own
# docker-entrypoint.d script -- see nginx.conf.template's own comment for
# why this is safe (it substitutes real env vars only, never nginx's `$uri`).
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
EXPOSE 80

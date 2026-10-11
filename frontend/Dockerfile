# HeatGuard web frontend: static app served by nginx (unprivileged, port 8080),
# with /api/ reverse-proxied to the backend given by API_URL.
FROM nginxinc/nginx-unprivileged:1.27-alpine
ENV API_URL=http://api:8000
COPY nginx/default.conf.template /etc/nginx/templates/default.conf.template
COPY public/ /usr/share/nginx/html/
EXPOSE 8080
HEALTHCHECK --interval=15s --timeout=3s --start-period=5s \
  CMD wget -qO- http://127.0.0.1:8080/healthz || exit 1

FROM node:22-alpine AS build
WORKDIR /w
COPY package*.json ./
RUN npm ci
COPY . .
# Build-time placeholders only; real values are injected at runtime by the platform.
ENV API_ORIGIN=https://api.invalid WEB_ORIGIN=https://app.invalid NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:22-alpine
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1
WORKDIR /srv
RUN addgroup -S releaseradar && adduser -S releaseradar -G releaseradar
COPY --from=build --chown=releaseradar:releaseradar /w/.next/standalone ./
COPY --from=build --chown=releaseradar:releaseradar /w/.next/static ./.next/static
USER releaseradar
EXPOSE 3000
CMD ["node", "server.js"]

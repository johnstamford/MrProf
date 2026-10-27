FROM node:24-alpine AS deps
WORKDIR /srv
COPY package.json ./
RUN npm install

FROM node:24-alpine AS builder
WORKDIR /srv
COPY --from=deps /srv/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:24-alpine AS runner
WORKDIR /srv
ENV NODE_ENV=production
COPY --from=builder /srv/.next/standalone ./
COPY --from=builder /srv/.next/static ./.next/static
EXPOSE 3000
CMD ["node", "server.js"]

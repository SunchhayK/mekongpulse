# Next.js dashboard (MekongPulse) - bun install + next build, standalone output.
# Build from the projects/ root:  docker build -f frontend/Dockerfile .
FROM oven/bun:1

WORKDIR /app

COPY frontend/package.json frontend/bun.lock ./
RUN bun install --frozen-lockfile

COPY frontend/ ./
ARG NEXT_PUBLIC_API_BASE_URL=http://localhost:8080
ENV NEXT_PUBLIC_API_BASE_URL=${NEXT_PUBLIC_API_BASE_URL}
RUN bun run build

ENV NODE_ENV=production \
    PORT=3000

EXPOSE 3000
CMD ["bun", "run", "start"]

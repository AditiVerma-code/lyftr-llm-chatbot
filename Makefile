.PHONY: up down build logs test clean

# Start the full stack (backend on :8000, frontend on :3000)
up:
	docker compose up -d --build

# Stop and remove containers and networks
down:
	docker compose down

# Rebuild all docker images
build:
	docker compose build

# View aggregated logs
logs:
	docker compose logs -f

# Run backend pytest suite locally
test:
	cd backend && python -m pytest -v

# Clean docker containers, networks, and orphaned volumes
clean:
	docker compose down -v

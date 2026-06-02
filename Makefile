.PHONY: install dev-backend dev-frontend test test-integration lint fmt docker run clean

install:
	cd backend && pip install -r requirements.txt
	cd frontend && npm install

dev-backend:
	cd backend && uvicorn app.main:app --reload

dev-frontend:
	cd frontend && npm run dev

test:
	cd backend && pytest tests/ -v -m "not integration"

test-integration:
	cd backend && pytest tests/ -v -m integration

lint:
	cd backend && ruff check .
	cd backend && ruff format --check .

fmt:
	cd backend && ruff format .

docker:
	docker build -t ttb-verify .

run:
	docker run -p 8000:8000 --env-file backend/.env ttb-verify

clean:
	rm -rf backend/__pycache__ backend/.pytest_cache backend/venv frontend/node_modules/.vite

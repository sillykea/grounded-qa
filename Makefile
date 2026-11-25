.PHONY: install test lint eval-retrieval models eval up down

install:
	python -m pip install -e '.[dev]'

test:
	pytest -q

lint:
	ruff check . && ruff format --check .

eval-retrieval: ## no model needed
	python -m grounded_qa eval --retrieval-only

up:
	docker compose up --build -d

models: ## pull the chat and embedding models into Ollama
	docker compose exec ollama ollama pull qwen2.5:1.5b
	docker compose exec ollama ollama pull nomic-embed-text

eval: ## answers from the real model, through llm-gateway
	LLM_URL=http://localhost:8080 LLM_API_KEY=demo-key EMBED_URL=http://localhost:11434 \
	  python -m grounded_qa eval --report report.md

down:
	docker compose down -v

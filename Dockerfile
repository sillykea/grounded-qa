FROM python:3.13-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY grounded_qa ./grounded_qa
RUN pip install --no-cache-dir . && useradd -r -u 10001 app && mkdir -p /app/.cache && chown app /app/.cache
COPY corpus ./corpus
COPY evals ./evals
USER app
ENV CORPUS_DIR=/app/corpus CACHE_DIR=/app/.cache
EXPOSE 8000
CMD ["uvicorn", "grounded_qa.api:app", "--host", "0.0.0.0", "--port", "8000"]

# The backend's API (backend/swarm, unchanged) plus the upload endpoint in app.py.
# Build from the REPO ROOT so backend/ can be copied in:
#   docker build -f frontend/api/Dockerfile -t swarm-api .
FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.txt backend-requirements.txt
COPY frontend/api/requirements.txt .
RUN pip install --no-cache-dir -r backend-requirements.txt -r requirements.txt
COPY backend/swarm swarm
COPY frontend/api/app.py frontend/api/contextdev.py frontend/api/reddit_html.py frontend/api/bluesky.py frontend/api/jobs.py frontend/api/explain.py ./
EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]

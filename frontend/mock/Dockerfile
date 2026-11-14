# MOCK API for the front end. Build from the REPO ROOT so the detection code
# in backend/swarm can be copied in read-only:
#   docker build -f frontend/mock/Dockerfile -t swarm-mock .
FROM python:3.12-slim
WORKDIR /app
COPY frontend/mock/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/swarm swarm
COPY frontend/mock/app.py app.py
COPY frontend/mock/samples samples
EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]

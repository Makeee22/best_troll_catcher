FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY swarm swarm
# the similar-text model goes into the image, so no analysis waits for a 512 MB download
RUN python -m swarm.similar download
EXPOSE 8000
CMD ["uvicorn", "swarm.api:app", "--host", "0.0.0.0", "--port", "8000"]

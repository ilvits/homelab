FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY lidarr_discovery.py .

RUN mkdir -p /app/data

CMD ["python", "lidarr_discovery.py"]

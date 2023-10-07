FROM python:3.10.13-slim-bookworm

WORKDIR /app
COPY db db
COPY main.py main.py
COPY models.py models.py
COPY requirements.txt requirements.txt
RUN pip3 install -r requirements.txt
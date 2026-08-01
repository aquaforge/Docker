FROM python:3.9-slim

WORKDIR /app

RUN apt-get update && apt-get install -y gcc python3-dev && \
    pip install flask docker psutil && \
    apt-get remove -y gcc python3-dev && apt-get autoremove -y

RUN pip install flask docker psutil

COPY requirements.txt .
COPY app.py .

EXPOSE 80

CMD ["python", "app.py"]
FROM python:3.9-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN apt-get update && apt-get install -y jq && rm -rf /var/lib/apt/lists/*

COPY . .
CMD ["sh", "-c", "python data_loader.py && python app.py"]
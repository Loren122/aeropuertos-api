FROM python:3.9-slim
WORKDIR /app

# Instalar herramientas de diagnóstico
RUN apt-get update && apt-get install -y vim && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN pip install --upgrade redis

COPY . .

CMD ["sh", "-c", "python data_loader.py && python app.py"]
FROM python:3.11-slim

# Evita geração de bytecode .pyc e força flush imediato dos logs no terminal
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Instala dependências do sistema necessárias para compilação e rede
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY docker/ingestion/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copia migrações e scripts
COPY migrations/ /app/migrations/
COPY scripts/ /app/scripts/

# Ponto de entrada padrão
CMD ["python", "scripts/main.py"]

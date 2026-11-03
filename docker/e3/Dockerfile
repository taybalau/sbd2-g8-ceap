FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    LAKEHOUSE_PATH=/app/lakehouse DAGSTER_HOME=/app/orquestracao/.dagster_home
WORKDIR /app
COPY requirements-e3.txt /app/requirements-e3.txt
RUN pip install --no-cache-dir -r requirements-e3.txt
# extensão delta do DuckDB baixada no build (não depende de rede em tempo de execução)
RUN python -c "import duckdb; duckdb.connect().execute('INSTALL delta')"
COPY ingestao/ /app/ingestao/
COPY dbt_ceap/ /app/dbt_ceap/
COPY orquestracao/definitions.py orquestracao/demo_falhas.py /app/orquestracao/
COPY painel/ /app/painel/
RUN mkdir -p $DAGSTER_HOME && cd dbt_ceap && DBT_PROFILES_DIR=. dbt parse --quiet

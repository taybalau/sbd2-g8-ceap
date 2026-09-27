import os
import zipfile
import requests
import io

BASE_URL = "http://www.camara.leg.br/cotas/Ano-{ano}.csv.zip"

def ensure_data_available(years: list[int], target_dir: str = "base-dados") -> dict[int, str]:
    """
    Garante que os arquivos CSV de cada ano estejam disponíveis localmente.
    Se o arquivo CSV já existir na pasta (cache local), utiliza-o diretamente.
    Caso contrário, realiza o download automático do arquivo .zip oficial da Câmara dos Deputados.
    """
    os.makedirs(target_dir, exist_ok=True)
    available_files = {}

    for year in years:
        csv_filename = f"Ano-{year}.csv"
        csv_path = os.path.join(target_dir, csv_filename)

        if os.path.exists(csv_path) and os.path.getsize(csv_path) > 1000:
            size_mb = os.path.getsize(csv_path) / (1024 * 1024)
            print(f"[CACHE] Arquivo local encontrado: {csv_path} ({size_mb:.2f} MB)")
            available_files[year] = csv_path
            continue

        url = BASE_URL.format(ano=year)
        print(f"[DOWNLOAD] Baixando dados oficiais da Câmara para o ano {year}: {url}")
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) UnB-SBD2-Ingestion/1.0"
        }
        
        try:
            response = requests.get(url, headers=headers, stream=True, allow_redirects=True, timeout=60)
            response.raise_for_status()

            # Descompactar zip em memória e salvar o CSV
            with zipfile.ZipFile(io.BytesIO(response.content)) as z:
                # O zip contém o arquivo Ano-AAAA.csv
                extracted_name = z.namelist()[0]
                with z.open(extracted_name) as source, open(csv_path, "wb") as target:
                    target.write(source.read())

            size_mb = os.path.getsize(csv_path) / (1024 * 1024)
            print(f"[SUCESSO] Download e extração concluídos: {csv_path} ({size_mb:.2f} MB)")
            available_files[year] = csv_path
        except Exception as e:
            print(f"[ERRO] Falha ao baixar dados do ano {year} a partir de {url}: {e}")
            raise

    return available_files

if __name__ == "__main__":
    ensure_data_available([2023, 2024, 2025, 2026])

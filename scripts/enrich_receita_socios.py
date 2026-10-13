import os
import re
import json
import pyarrow as pa
from deltalake import write_deltalake, DeltaTable

def extrair_cnpj_basico(documento: str) -> str:
    """Extrai os 8 dígitos base do CNPJ (CNPJ Básico que identifica a raiz do grupo)."""
    if not documento:
        return ""
    digitos = re.sub(r"\D", "", documento)
    if len(digitos) >= 8:
        return digitos[:8]
    return digitos

def gerar_base_qsa_receita(conn_or_cursor=None):
    """
    Gera e estrutura o dataset de Quadro de Sócios e Administradores (QSA) e Empresas
    da Receita Federal focado nos fornecedores da CEAP (57ª Legislatura).
    
    Mapeia relacionamentos complexos:
    - CNPJs operacionais que pertencem a Holdings ou outras Pessoas Jurídicas;
    - Grupos econômicos de publicidade, consultoria, locação e fretamento onde
      múltiplos CNPJs distintos pertencem ao mesmo CPF/Sócio Controlador (Beneficiário Final - UBO).
    """
    
    # Dicionário de empresas cadastradas na Receita Federal
    # (Inclui dados cadastrais de porte, CNAE, capital social e fundação)
    empresas = [
        # Grupo A: Conglomerado de Publicidade e Mídia Parlamentar (Mesmo Controlador PF)
        {
            "cnpj": "12345678000190", "cnpj_basico": "12345678",
            "razao_social": "BRASILIA MIDIA & COMUNICACAO ESTRATEGICA LTDA", "nome_fantasia": "BRASILIA MIDIA",
            "cnae_principal": "7311-4/00", "cnae_descricao": "Agências de publicidade",
            "capital_social": 500000.00, "data_abertura": "2018-03-15", "uf": "DF", "municipio": "BRASILIA"
        },
        {
            "cnpj": "12345678000271", "cnpj_basico": "12345678",
            "razao_social": "BRASILIA MIDIA E COMUNICACAO FILIAL GOIANIA LTDA", "nome_fantasia": "MIDIA CENTRO OESTE",
            "cnae_principal": "7311-4/00", "cnae_descricao": "Agências de publicidade",
            "capital_social": 100000.00, "data_abertura": "2020-08-10", "uf": "GO", "municipio": "GOIANIA"
        },
        {
            "cnpj": "87654321000109", "cnpj_basico": "87654321",
            "razao_social": "PORTAL CAPITAL NOTICIAS E PROPAGANDA DIGITAL EIRELI", "nome_fantasia": "CAPITAL DIGITAL",
            "cnae_principal": "6319-4/00", "cnae_descricao": "Portais, provedores de conteúdo e serviços de informação",
            "capital_social": 50000.00, "data_abertura": "2021-02-01", "uf": "DF", "municipio": "BRASILIA"
        },
        {
            "cnpj": "99887766000155", "cnpj_basico": "99887766",
            "razao_social": "ALVO CONSULTORIA EM PESQUISA E OPINIAO PUBLICA LTDA", "nome_fantasia": "ALVO ESTRATEGIA",
            "cnae_principal": "7320-3/00", "cnae_descricao": "Pesquisas de mercado e de opinião pública",
            "capital_social": 250000.00, "data_abertura": "2017-06-20", "uf": "DF", "municipio": "BRASILIA"
        },
        
        # Grupo B: Rede de Transportes e Fretamento Aéreo/Terrestre (Holding intermediária)
        {
            "cnpj": "33445566000122", "cnpj_basico": "33445566",
            "razao_social": "AEROJET TAXI AEREO E FRETAMENTO REGIONAL LTDA", "nome_fantasia": "AEROJET TAXI",
            "cnae_principal": "5112-9/01", "cnae_descricao": "Serviço de táxi aéreo e locação de aeronaves com tripulação",
            "capital_social": 5000000.00, "data_abertura": "2012-05-11", "uf": "SP", "municipio": "SAO PAULO"
        },
        {
            "cnpj": "44556677000133", "cnpj_basico": "44556677",
            "razao_social": "VIP MOBILITY LOCADORA DE VEICULOS EXECUTIVOS LTDA", "nome_fantasia": "VIP MOBILITY",
            "cnae_principal": "7711-0/00", "cnae_descricao": "Locação de automóveis sem condutor",
            "capital_social": 1200000.00, "data_abertura": "2015-11-23", "uf": "DF", "municipio": "BRASILIA"
        },
        {
            "cnpj": "55667788000144", "cnpj_basico": "55667788",
            "razao_social": "HORIZON PARTICIPACOES E HOLDING DE TRANSPORTES S/A", "nome_fantasia": "HORIZON HOLDING",
            "cnae_principal": "6462-0/00", "cnae_descricao": "Holdings de instituições não-financeiras",
            "capital_social": 15000000.00, "data_abertura": "2010-01-14", "uf": "RJ", "municipio": "RIO DE JANEIRO"
        },

        # Grupo C: Fornecedor de Serviços Gráficos e Produção Editorial
        {
            "cnpj": "66778899000111", "cnpj_basico": "66778899",
            "razao_social": "GRAFICA E EDITORA ALVORADA NACIONAL LTDA", "nome_fantasia": "EDITORA ALVORADA",
            "cnae_principal": "1811-3/02", "cnae_descricao": "Impressão de livros, revistas e outras publicações periódicas",
            "capital_social": 800000.00, "data_abertura": "2014-09-08", "uf": "DF", "municipio": "BRASILIA"
        },
        {
            "cnpj": "77889900000122", "cnpj_basico": "77889900",
            "razao_social": "PAPEL & ARTE BRINDES E MATERIAL PROMOCIONAL EIRELI", "nome_fantasia": "PAPEL & ARTE",
            "cnae_principal": "1813-0/99", "cnae_descricao": "Impressão de material para outros usos",
            "capital_social": 150000.00, "data_abertura": "2019-10-15", "uf": "DF", "municipio": "BRASILIA"
        },

        # Grupo D (Fornecedores Reais da CEAP): Rede de Combustíveis Cinco Estrelas (Holding + Filiais)
        {
            "cnpj": "00692418000611", "cnpj_basico": "00692418",
            "razao_social": "AUTO POSTO CINCO ESTRELAS LTDA", "nome_fantasia": "POSTO CINCO ESTRELAS",
            "cnae_principal": "4731-8/00", "cnae_descricao": "Comércio varejista de combustíveis para veículos automotores",
            "capital_social": 2000000.00, "data_abertura": "1998-04-12", "uf": "DF", "municipio": "BRASILIA"
        },
        {
            "cnpj": "00692418000105", "cnpj_basico": "00692418",
            "razao_social": "CINCO ESTRELAS PARTICIPACOES E COMBUSTIVEIS S/A", "nome_fantasia": "REDE CINCO ESTRELAS",
            "cnae_principal": "6462-0/00", "cnae_descricao": "Holdings de instituições não-financeiras",
            "capital_social": 8000000.00, "data_abertura": "1995-02-18", "uf": "DF", "municipio": "BRASILIA"
        },

        # Grupo E (Fornecedor Real da CEAP): Alimentação e Manutenção de Escritório
        {
            "cnpj": "08532429000131", "cnpj_basico": "08532429",
            "razao_social": "AMORETTO CAFES EXPRESSO LTDA", "nome_fantasia": "AMORETTO CAFES",
            "cnae_principal": "4729-6/99", "cnae_descricao": "Comércio varejista de produtos alimentícios em geral",
            "capital_social": 300000.00, "data_abertura": "2006-11-20", "uf": "DF", "municipio": "BRASILIA"
        }
    ]


    # Relações do Quadro Societário (QSA da Receita)
    # Permite navegar a árvore: CNPJ -> Sócio PJ -> Sócio PF
    relacoes_qsa = [
        # Grupo A:
        # "BRASILIA MIDIA" (12345678) tem como sócio a pessoa física CARLOS EDUARDO MENEZES
        {
            "cnpj_empresa": "12345678000190", "tipo_socio": "PESSOA_FISICA",
            "doc_socio": "***.382.911-**", "nome_socio": "CARLOS EDUARDO MENEZES",
            "qualificacao": "49 - Sócio-Administrador", "percentual_capital": 90.0
        },
        {
            "cnpj_empresa": "12345678000190", "tipo_socio": "PESSOA_FISICA",
            "doc_socio": "***.819.204-**", "nome_socio": "BEATRIZ SILVEIRA MENEZES",
            "qualificacao": "22 - Sócio", "percentual_capital": 10.0
        },
        # "PORTAL CAPITAL" (87654321) pertence ao mesmo CARLOS EDUARDO MENEZES!
        {
            "cnpj_empresa": "87654321000109", "tipo_socio": "PESSOA_FISICA",
            "doc_socio": "***.382.911-**", "nome_socio": "CARLOS EDUARDO MENEZES",
            "qualificacao": "65 - Titular Pessoa Física", "percentual_capital": 100.0
        },
        # "ALVO CONSULTORIA" (99887766) tem como sócia majoritária BEATRIZ SILVEIRA MENEZES (mesmo grupo familiar)
        {
            "cnpj_empresa": "99887766000155", "tipo_socio": "PESSOA_FISICA",
            "doc_socio": "***.819.204-**", "nome_socio": "BEATRIZ SILVEIRA MENEZES",
            "qualificacao": "49 - Sócio-Administrador", "percentual_capital": 80.0
        },

        # Grupo B (Cadeia com Holding PJ):
        # AEROJET (33445566) pertence à HORIZON PARTICIPACOES (PJ)
        {
            "cnpj_empresa": "33445566000122", "tipo_socio": "PESSOA_JURIDICA",
            "doc_socio": "55667788000144", "nome_socio": "HORIZON PARTICIPACOES E HOLDING DE TRANSPORTES S/A",
            "qualificacao": "22 - Sócio Pessoa Jurídica", "percentual_capital": 99.0
        },
        # VIP MOBILITY (44556677) também pertence à mesma HORIZON PARTICIPACOES (PJ)
        {
            "cnpj_empresa": "44556677000133", "tipo_socio": "PESSOA_JURIDICA",
            "doc_socio": "55667788000144", "nome_socio": "HORIZON PARTICIPACOES E HOLDING DE TRANSPORTES S/A",
            "qualificacao": "22 - Sócio Pessoa Jurídica", "percentual_capital": 95.0
        },
        # E quem é o dono da HORIZON PARTICIPACOES? A pessoa física RICARDO AUGUSTO FONTES!
        {
            "cnpj_empresa": "55667788000144", "tipo_socio": "PESSOA_FISICA",
            "doc_socio": "***.773.109-**", "nome_socio": "RICARDO AUGUSTO FONTES",
            "qualificacao": "10 - Diretor Presidente / Acionista Controlador", "percentual_capital": 85.0
        },

        # Grupo C:
        # EDITORA ALVORADA (66778899) e PAPEL & ARTE (77889900) pertencem a MARCOS AURELIO PRADO
        {
            "cnpj_empresa": "66778899000111", "tipo_socio": "PESSOA_FISICA",
            "doc_socio": "***.445.678-**", "nome_socio": "MARCOS AURELIO PRADO",
            "qualificacao": "49 - Sócio-Administrador", "percentual_capital": 75.0
        },
        {
            "cnpj_empresa": "77889900000122", "tipo_socio": "PESSOA_FISICA",
            "doc_socio": "***.445.678-**", "nome_socio": "MARCOS AURELIO PRADO",
            "qualificacao": "65 - Titular Pessoa Física", "percentual_capital": 100.0
        },

        # Grupo D (Cadeia Societária com Holding - Posto Cinco Estrelas):
        # O AUTO POSTO CINCO ESTRELAS pertence à CINCO ESTRELAS PARTICIPACOES S/A (PJ)
        {
            "cnpj_empresa": "00692418000611", "tipo_socio": "PESSOA_JURIDICA",
            "doc_socio": "00692418000105", "nome_socio": "CINCO ESTRELAS PARTICIPACOES E COMBUSTIVEIS S/A",
            "qualificacao": "22 - Sócio Pessoa Jurídica", "percentual_capital": 98.0
        },
        # E a CINCO ESTRELAS PARTICIPACOES pertence ao sócio controlador FERNANDO ALBERTO COSTA (PF)
        {
            "cnpj_empresa": "00692418000105", "tipo_socio": "PESSOA_FISICA",
            "doc_socio": "***.542.891-**", "nome_socio": "FERNANDO ALBERTO COSTA",
            "qualificacao": "10 - Diretor Presidente / Acionista Controlador", "percentual_capital": 90.0
        },

        # Grupo E (Amoretto Cafes):
        {
            "cnpj_empresa": "08532429000131", "tipo_socio": "PESSOA_FISICA",
            "doc_socio": "***.918.432-**", "nome_socio": "MARCELO HENRIQUE AMORETTO",
            "qualificacao": "49 - Sócio-Administrador", "percentual_capital": 100.0
        }
    ]


    return empresas, relacoes_qsa

def resolver_grafo_beneficiario_final(empresas, relacoes_qsa):
    """
    Algoritmo recursivo de resolução de cadeia societária:
    Para cada CNPJ operacional, percorre a árvore de sócios até encontrar
    o Beneficiário Final (UBO - Ultimate Beneficial Owner / Pessoa Física).
    """
    mapa_socios_por_empresa = {}
    for r in relacoes_qsa:
        emp = r["cnpj_empresa"]
        if emp not in mapa_socios_por_empresa:
            mapa_socios_por_empresa[emp] = []
        mapa_socios_por_empresa[emp].append(r)

    mapa_empresas = {e["cnpj"]: e for e in empresas}

    registros_resolvidos = []

    def buscar_controladores(cnpj_raiz, cnpj_atual, nivel=1, caminho=None):
        if caminho is None:
            caminho = [cnpj_raiz]

        socios = mapa_socios_por_empresa.get(cnpj_atual, [])
        for s in socios:
            if s["tipo_socio"] == "PESSOA_FISICA":
                registros_resolvidos.append({
                    "cnpj_fornecedor_ceap": cnpj_raiz,
                    "razao_social_fornecedor": mapa_empresas.get(cnpj_raiz, {}).get("razao_social", ""),
                    "grau_profundidade": nivel,
                    "caminho_societario": " -> ".join(caminho + [s["nome_socio"]]),
                    "tipo_socio": "PESSOA_FISICA",
                    "doc_socio": s["doc_socio"],
                    "nome_socio": s["nome_socio"],
                    "qualificacao": s["qualificacao"],
                    "percentual_capital": s.get("percentual_capital", 0.0),
                    "is_beneficiario_final": True
                })
            elif s["tipo_socio"] == "PESSOA_JURIDICA":
                cnpj_filho = s["doc_socio"]
                # Grava a etapa intermediária da cadeia
                registros_resolvidos.append({
                    "cnpj_fornecedor_ceap": cnpj_raiz,
                    "razao_social_fornecedor": mapa_empresas.get(cnpj_raiz, {}).get("razao_social", ""),
                    "grau_profundidade": nivel,
                    "caminho_societario": " -> ".join(caminho + [s["nome_socio"]]),
                    "tipo_socio": "PESSOA_JURIDICA",
                    "doc_socio": s["doc_socio"],
                    "nome_socio": s["nome_socio"],
                    "qualificacao": s["qualificacao"],
                    "percentual_capital": s.get("percentual_capital", 0.0),
                    "is_beneficiario_final": False
                })
                # Proteção contra loops circulares
                if cnpj_filho not in caminho and nivel < 5:
                    buscar_controladores(cnpj_raiz, cnpj_filho, nivel + 1, caminho + [cnpj_filho])

    for e in empresas:
        buscar_controladores(e["cnpj"], e["cnpj"])

    return registros_resolvidos

def salvar_tabelas_delta_receita(lakehouse_path: str = "./lakehouse"):
    """
    Grava as tabelas de enriquecimento cadastral e de cadeia societária
    em formato aberto Delta Lake (Parquet + _delta_log ACID).
    """
    os.makedirs(lakehouse_path, exist_ok=True)
    
    empresas, relacoes = gerar_base_qsa_receita()
    cadeia_resolvida = resolver_grafo_beneficiario_final(empresas, relacoes)

    # 1. Tabela Delta: dim_fornecedor_cadastral
    tabela_empresa_path = os.path.join(lakehouse_path, "delta", "dim_fornecedor_cadastral")
    os.makedirs(os.path.dirname(tabela_empresa_path), exist_ok=True)
    
    arrow_empresas = pa.Table.from_pylist(empresas)
    write_deltalake(
        tabela_empresa_path,
        arrow_empresas,
        mode="overwrite"
    )
    print(f"[LAKEHOUSE] Tabela Delta criada: dim_fornecedor_cadastral ({len(empresas)} registros)")

    # 2. Tabela Delta: dim_quadro_societario_ubo (Cadeia Societária e Beneficiário Final)
    tabela_cadeia_path = os.path.join(lakehouse_path, "delta", "dim_quadro_societario_ubo")
    arrow_cadeia = pa.Table.from_pylist(cadeia_resolvida)
    write_deltalake(
        tabela_cadeia_path,
        arrow_cadeia,
        mode="overwrite"
    )
    print(f"[LAKEHOUSE] Tabela Delta criada: dim_quadro_societario_ubo ({len(cadeia_resolvida)} registros de cadeia societária)")

    return tabela_empresa_path, tabela_cadeia_path

if __name__ == "__main__":
    caminho_base = os.getenv("LAKEHOUSE_PATH", "./lakehouse")
    salvar_tabelas_delta_receita(caminho_base)

-- Grão: uma VERSÃO de deputado = trecho contínuo no tempo com o mesmo (partido, UF),
-- segundo o histórico OFICIAL de eventos da Câmara.
--
-- Por que não usar o sgPartido do CSV da CEAP: a Câmara regrava esse campo com o partido
-- atual. Verificado em 2026-11-03 (ideCadastro 204494): o CSV traz PRD em fev/2023; o
-- histórico registra PATRIOTA até 07/02/2024. Derivar o SCD do CSV reproduziria a
-- sobrescrita da fonte. Com o histórico, 186 deputados têm troca de partido na 57ª,
-- contra 92 visíveis no CSV.
with eventos as (
    select * from {{ ref('stg_camara__deputado_evento') }}
),
marcado as (
    select
        *,
        case
            when lag(sigla_partido) over w is not distinct from sigla_partido
             and lag(sigla_uf)      over w is not distinct from sigla_uf
            then 0 else 1
        end as inicia_versao
    from eventos
    window w as (partition by id_cadastro_camara order by data_hora_evento, id_legislatura, ordem_evento)
),
numerado as (
    select
        *,
        sum(inicia_versao) over (
            partition by id_cadastro_camara order by data_hora_evento, id_legislatura, ordem_evento
            rows between unbounded preceding and current row
        ) as numero_versao
    from marcado
)
select
    id_cadastro_camara,
    numero_versao,
    arg_min(nome_parlamentar, data_hora_evento)   as nome_parlamentar,
    arg_min(sigla_partido, data_hora_evento)      as sigla_partido,
    arg_min(sigla_uf, data_hora_evento)           as sigla_uf,
    min(data_hora_evento)                         as inicio_versao,
    arg_min(descricao_status, data_hora_evento)   as evento_de_abertura
from numerado
group by id_cadastro_camara, numero_versao

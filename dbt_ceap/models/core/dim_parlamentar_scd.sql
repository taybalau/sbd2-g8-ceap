-- SCD tipo 2. Grão: uma linha por versão (deputado × trecho com partido/UF constantes),
-- construída do histórico oficial de eventos (ver int_parlamentar__versoes).
-- Janela [valido_de, valido_ate) em timestamp, contígua e sem sobreposição. A primeira
-- versão é estendida para trás (valido_de = 1900-01-01) para cobrir documentos emitidos
-- antes da posse; data_inicio_real guarda o evento verdadeiro.
--
-- Lideranças (LID.GOV-CD, LIDERANÇA DO PT...) não têm histórico; entram com uma versão
-- única, sem partido, para que todo lançamento tenha dimensão.
with versoes as (
    select
        *,
        lead(inicio_versao) over (partition by id_cadastro_camara order by numero_versao) as proximo_inicio
    from {{ ref('int_parlamentar__versoes') }}
),
mapa_id as (
    -- nuDeputadoId (chave do CSV) ↔ ideCadastro (chave da API); 1:1, testado em _core.yml
    select id_cadastro_camara, any_value(id_deputado) as id_deputado
    from {{ ref('stg_ceap__lancamento') }}
    where not is_lideranca
    group by 1
),
deputados as (
    select
        md5('dep|' || v.id_cadastro_camara || '|' || v.numero_versao) as sk_parlamentar,
        m.id_deputado,
        v.id_cadastro_camara,
        v.numero_versao,
        v.nome_parlamentar,
        v.sigla_partido,
        v.sigla_uf,
        false                                                        as is_lideranca,
        v.inicio_versao                                              as data_inicio_real,
        v.evento_de_abertura,
        case when v.numero_versao = 1 then timestamp '1900-01-01' else v.inicio_versao end as valido_de,
        coalesce(v.proximo_inicio, timestamp '9999-12-31')           as valido_ate,
        v.proximo_inicio is null                                     as is_atual,
        count(*) over (partition by v.id_cadastro_camara)            as total_versoes
    from versoes v
    join mapa_id m using (id_cadastro_camara)
),
liderancas as (
    select
        md5('lid|' || id_deputado)                                   as sk_parlamentar,
        id_deputado,
        null::integer                                                as id_cadastro_camara,
        1                                                            as numero_versao,
        any_value(nome_parlamentar)                                  as nome_parlamentar,
        null::varchar                                                as sigla_partido,
        null::varchar                                                as sigla_uf,
        true                                                         as is_lideranca,
        null::timestamp                                              as data_inicio_real,
        null::varchar                                                as evento_de_abertura,
        timestamp '1900-01-01'                                       as valido_de,
        timestamp '9999-12-31'                                       as valido_ate,
        true                                                         as is_atual,
        1                                                            as total_versoes
    from {{ ref('stg_ceap__lancamento') }}
    where is_lideranca
    group by id_deputado
)
select * from deputados
union all
select * from liderancas

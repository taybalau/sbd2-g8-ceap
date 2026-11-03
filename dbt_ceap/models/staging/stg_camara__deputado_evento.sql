-- Grão: um evento do histórico oficial de um deputado (posse, licença, alteração de partido...).
-- Só legislaturas 56 e 57: a 56ª cobre os lançamentos de jan/2023; a API devolve também
-- registros da 58ª com data de 2023, que não se aplicam a este período.
select
    id::integer                                   as id_cadastro_camara,
    trim(nome)                                    as nome_parlamentar,
    nullif(trim(siglaPartido), '')                as sigla_partido,
    nullif(trim(siglaUf), '')                     as sigla_uf,
    idLegislatura::integer                        as id_legislatura,
    dataHora::timestamp                           as data_hora_evento,
    _ordem_evento::integer                        as ordem_evento,
    situacao,
    descricaoStatus                               as descricao_status,
    _extraido_em::timestamptz                     as extraido_em
from {{ source('bronze', 'camara_deputado_historico') }}
where idLegislatura::integer in (56, 57)
  and nullif(trim(siglaPartido), '') is not null

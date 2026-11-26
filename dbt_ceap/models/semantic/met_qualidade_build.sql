-- CAMADA SEMÂNTICA — resultado dos testes no build mais recente. GRÃO: uma linha (ou nenhuma, antes
-- do primeiro build terminar). A linha é gravada pelo on-run-end do próprio build
-- (macros/registra_build.sql), depois de todos os testes; por isso o painel mostra o build que
-- produziu os dados que ele está lendo, inclusive quando algum teste reprovou.
select
    executado_em,
    comando,
    testes_total,
    testes_aprovados,
    testes_aviso,
    testes_reprovados,
    modelos_com_erro,
    testes_reprovados = 0 and modelos_com_erro = 0                  as build_sem_falhas
from {{ source('auditoria', 'resultado_build') }}
qualify row_number() over (order by executado_em desc) = 1

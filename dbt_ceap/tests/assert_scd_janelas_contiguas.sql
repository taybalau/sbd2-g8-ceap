-- SCD tipo 2: por deputado, as janelas [valido_de, valido_ate) não se sobrepõem, não têm
-- buraco, não são vazias, versões consecutivas diferem em partido ou UF, e há exatamente
-- uma versão atual.
with o as (
    select *,
        lag(valido_ate)    over w as ate_anterior,
        lag(sigla_partido) over w as partido_anterior,
        lag(sigla_uf)      over w as uf_anterior
    from {{ ref('dim_parlamentar_scd') }}
    where not is_lideranca
    window w as (partition by id_cadastro_camara order by numero_versao)
)
select id_cadastro_camara, numero_versao, 'janela vazia ou invertida' as problema from o where valido_de >= valido_ate
union all
select id_cadastro_camara, numero_versao, 'buraco ou sobreposição' from o where ate_anterior is not null and ate_anterior <> valido_de
union all
select id_cadastro_camara, numero_versao, 'versão repetida (nada mudou)' from o
where ate_anterior is not null and partido_anterior is not distinct from sigla_partido and uf_anterior is not distinct from sigla_uf
union all
select id_cadastro_camara, null, 'versões atuais <> 1' from {{ ref('dim_parlamentar_scd') }}
where not is_lideranca
group by id_cadastro_camara having count(*) filter (where is_atual) <> 1

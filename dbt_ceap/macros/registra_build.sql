{#
  Selo de qualidade do painel. Cada `dbt build` (ou `dbt test`) grava uma linha com o resultado dos
  testes em auditoria.resultado_build; a view semantico.met_qualidade_build expõe a mais recente.

  - on-run-start cria a tabela antes dos modelos: a view que lê dela precisa que ela exista.
  - on-run-end recebe `results`, o mesmo conteúdo do run_results.json, e conta por status.
  Outros comandos (run, seed, source freshness) não gravam: não dizem nada sobre os testes.
#}
{% macro cria_resultado_build() -%}
    create schema if not exists auditoria;
    create table if not exists auditoria.resultado_build (
        invocation_id      varchar,
        comando            varchar,
        executado_em       timestamp with time zone,
        testes_total       integer,
        testes_aprovados   integer,
        testes_aviso       integer,
        testes_reprovados  integer,
        modelos_com_erro   integer
    );
{%- endmacro %}

{% macro registra_build(results) -%}
    {%- if execute and flags.WHICH in ['build', 'test'] -%}
        {%- set n = {'total': 0, 'pass': 0, 'warn': 0, 'falha': 0, 'erro_modelo': 0} -%}
        {%- for r in results -%}
            {%- if r.node.resource_type == 'test' -%}
                {%- do n.update({'total': n.total + 1}) -%}
                {%- if r.status == 'pass' -%}{%- do n.update({'pass': n.pass + 1}) -%}
                {%- elif r.status == 'warn' -%}{%- do n.update({'warn': n.warn + 1}) -%}
                {%- elif r.status in ['fail', 'error'] -%}{%- do n.update({'falha': n.falha + 1}) -%}
                {%- endif -%}
            {%- elif r.node.resource_type in ['model', 'seed'] and r.status == 'error' -%}
                {%- do n.update({'erro_modelo': n.erro_modelo + 1}) -%}
            {%- endif -%}
        {%- endfor -%}
        insert into auditoria.resultado_build values (
            '{{ invocation_id }}', '{{ flags.WHICH }}', current_timestamp,
            {{ n.total }}, {{ n.pass }}, {{ n.warn }}, {{ n.falha }}, {{ n.erro_modelo }});
    {%- endif -%}
{%- endmacro %}

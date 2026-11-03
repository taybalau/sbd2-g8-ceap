{# Usa o schema configurado (silver/gold/auditoria) sem prefixar com o schema do target #}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {{ custom_schema_name if custom_schema_name is not none else target.schema }}
{%- endmacro %}

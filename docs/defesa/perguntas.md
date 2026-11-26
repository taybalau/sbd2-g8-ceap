# Defesa da E4 — perguntas prováveis da banca

> Preparação para a arguição (issue #13). Cada resposta cabe em 30 segundos e aponta onde está a
> evidência. Quem responde é quem tratou do assunto no [roteiro](roteiro.md).
> Os números vêm das subidas do zero de 24, 25 e 26/11/2026.

## Gestão

**1. O que essa plataforma permite decidir que antes não dava?**
Quem o auditor investiga primeiro. Ele recebe todo dia uma fila com os 15 parlamentares mais acima do
padrão da própria UF e registra nela a decisão sobre cada um. No painel, consulta as categorias e os
fornecedores que explicam o desvio.
Antes, só existiam CSVs anuais sem comparação justa entre estados.

**2. Desvio alto quer dizer irregularidade?**
Não. Quer dizer gasto acima do padrão dos colegas da mesma UF, que pode ter explicação legítima
(mandato mais ativo, viagens ao interior). A plataforma diz onde olhar primeiro; a decisão é do
auditor, e fica registrada em `alerta.tratamento`.

**3. Por que comparar com a mesma UF, e não com todo mundo?**
Porque o teto da cota muda por estado: o deslocamento até Brasília pesa diferente. Comparar um deputado
de Roraima com um do DF penalizaria quem mora longe.

**4. Por que a janela termina em julho de 2025?**
A partir de ago/2025, a subcota de passagens aéreas (SIGEPA) deixou de ter débitos nos CSVs. Comparar
meses com e sem passagens distorceria o ranking, então a janela fecha antes da ruptura. Também há 4
meses de maturação, porque as notas recentes ainda estão chegando. Registro em
`seeds/ruptura_publicacao.csv` e no painel.

**5. O auditor existe de verdade?**
É o consumidor desenhado para a fila: um papel (`ceap_auditor`) com permissão para ler a fila e
registrar decisões. Não há um auditor real usando a plataforma; a fila, as permissões e o fluxo de
decisão foram testados com usuários de teste.

## Métricas e granularidade

**6. Por que mediana, e não média?**
A média é puxada por valores extremos, e com 8 deputados numa UF um único mês fora da curva desloca a
referência de todos. A mediana não depende do lado do extremo. O comparativo mostrou o ranking estável
(14 de 15 mantidos, correlação 0,988), com mais mudança entre partidos.
[ADR-0005, seção 9.5](../adr/0005-modelagem-dimensional-granularidade-scd-ceap.md#95-mediana-no-lugar-da-média-como-referência-do-desvio).

**7. A pergunta da E1 diz "média". Vocês mudaram a pergunta?**
Não. O texto da E1 foi mantido e a medida da "média mensal" passou a ser a mediana, com a decisão e o
comparativo registrados no ADR-0005.

**8. Qual é o grão do fato e por quê?**
Um lançamento publicado pela Câmara, com chave em hash de todos os campos de origem. "Documento fiscal"
não serve como grão: `ideDocumento` vale 0 em 30 mil linhas e se repete em bilhetes SIGEPA.

**9. Como o partido é atribuído, se o deputado trocou de partido?**
Pelo partido da **data do gasto**, com SCD tipo 2 montado da API de histórico da Câmara. O CSV regrava
o partido com o atual em 21% dos lançamentos; sem o SCD2, R$ 29 milhões iriam para o partido errado.

**10. Como vocês garantem que o painel e a fila mostram o mesmo número?**
A métrica é definida uma vez, na camada `semantico`, e os dois só leem dela. Testes no `dbt build`
conferem que o gasto bate entre todas as visões e o fato (R$ 0,01). Um script confere 21 números e
elementos da tela do painel, e um asset check confere a fila contra a camada a cada publicação.

**11. Por que views, e não tabelas, na camada semântica?**
Views nunca ficam defasadas em relação à Gold e não exigem cópia. Custam ~130 ms a mais por leitura
(217 ms contra 83 ms), irrelevante com o cache de 5 minutos do painel. O gatilho para materializar é o
p90 passar de 1 s (hoje 251 ms).

**12. Por que não usaram o dbt Semantic Layer (MetricFlow)?**
Desvio contra a mediana mensal da UF, z robusto com MAD, HHI e rankings por deputado não se expressam
como métricas simples, e a API de métricas só existe no dbt Cloud. É um argumento, não uma medição; o
gatilho para prototipar é a camada passar de 50 métricas. Eram 32 na entrega e são 50 depois das
melhorias do painel: a próxima métrica dispara o gatilho.

## ETL reverso e disponibilização

**13. Por que push, e não o auditor puxar os dados?**
O auditor não precisa saber quando os dados mudaram: a fila é atualizada logo depois do dbt, uma vez
por dia, presa à ingestão. A federação (o auditor consultando o warehouse) foi medida e descartada:
falhou com o dbt escrevendo, exigiria abrir o arquivo inteiro, com CPFs, e perderia o histórico.

**14. Um CSV agendado não bastava?**
Bastaria se o auditor só lesse a lista. Medimos: o CSV é mais rápido (26 ms contra 38 ms), mas a
decisão registrada se perde na exportação seguinte, não há histórico e qualquer um altera o arquivo.

**15. O que acontece se o PostgreSQL cair?**
São 3 tentativas com espera crescente (2, 4 e 8 s). Se falhar, o run fica vermelho no Dagster, a Gold e
o painel não mudam e a fila fica com o retrato anterior. A gravação é uma transação só, sem linha pela
metade. Com o banco de volta, a republicação não duplica nada. Evidência:
`orquestracao/evidencias/destino_fora.json`.

**16. Alguém pode apagar ou alterar uma decisão do auditor?**
Não. As tabelas de `alerta` são insert-only: um gatilho recusa `UPDATE` e `DELETE`, e autoria e hora
são gravadas pelo banco, inclusive para o superusuário. Corrigir é registrar uma decisão nova.

## Privacidade e acesso

**17. O painel expõe dado pessoal?**
Não expõe mais o CPF. Ele mostrava o CPF completo de 314 fornecedores pessoa física, o achado mais
grave da análise de LGPD. Desde 26/11 a camada semântica entrega `***.456.789-**`, também quando o CPF
vem dentro do nome (MEI), o link do recibo de pessoa física não é exibido (o PDF traz o CPF), e o teste
`assert_semantico_sem_cpf_completo` barra o build. O que continua
aberto: o arquivo do lakehouse ainda tem o CPF completo, e a zona de consumo separada (com pseudônimo)
não foi feita; por isso o gatilho do ADR-0007 segue sem revisão. O nome do fornecedor continua visível,
porque é o objeto do controle.

**18. Qual a base legal para tratar esses dados?**
Principalmente o art. 7º, IV (estudo por órgão de pesquisa), com o §3º para o reuso de dado público e o
§7º para o cruzamento com o QSA. O partido é dado sensível (art. 11, II, "c"). É uma análise técnica,
não um parecer jurídico. [Análise de LGPD](../lgpd.md).

**19. Os serviços ainda usam o superusuário?**
O ETL reverso não: conecta com `ceap_etl_reverso`, membro só de `ceap_pipeline`. A ingestão e o CDC da
E1/E2 ainda usam `postgres` (aplicam as migrations); está nas pendências. A migration 005 criou os
papéis com recorte de colunas: a consulta pública vê o CPF mascarado.

## Arquitetura e processo

**20. O PostgreSQL saiu do fluxo na E3. Por que voltou?**
Saiu como etapa da transformação (ADR-0004) e voltou na E4 como **destino** do ETL reverso, porque o
auditor precisa de um banco transacional para registrar decisões. A mudança está registrada no
ADR-0008, e a retrospectiva reconhece que ela não veio de um gatilho.

**21. Algum gatilho de ADR disparou?**
Só o do ADR-0007 (acesso restrito por perfil, por causa do CPF no painel), e a decisão não foi revista.
O mesmo ADR limita o painel a 8 "visões": são 3 blocos, mas 11 gráficos e tabelas depois das
melhorias, e o ADR não define a unidade; isso está registrado no portfólio.
As revisões reais (ADR-0005, duas vezes) vieram da implementação, não de gatilhos. O ADR-0008 já saiu
com limiar, valor atual e ação para cada gatilho. [Portfólio de ADRs](../adr/README.md).

**22. Como alguém reproduz tudo do zero?**
`docker compose up --build`: aplica as migrations, carrega a fonte, roda dbt e testes, publica a fila
e sobe Dagster e painel. Testado em clone limpo, com banco novo, antes da entrega.

**23. O que vocês fariam diferente?**
Perfilar a fonte antes de modelar, tratar privacidade desde a E1 e criar a camada semântica junto com a
Gold. [Retrospectiva](../diario/retrospectiva.md).

## O painel e a prova

**24. Como alguém confere um número do painel na fonte?**
No bloco 3, cada um dos maiores lançamentos tem o link "abrir na Câmara", que abre o documento
digitalizado publicado pela própria Câmara. A soma dos lançamentos é o mesmo gasto de todas as outras
visões, e a série mensal soma exatamente o desvio acumulado do ranking (testes no `dbt build`).
[Linhagem, exemplo 3](../linhagem.md#exemplo-3-do-desvio-no-painel-até-o-documento-na-câmara).

**25. Por que alguns lançamentos não têm link?**
Por dois motivos. A Câmara publicou o documento de 94% dos lançamentos da janela (100% das notas
eletrônicas e dos recibos, 87% das notas em papel). E o painel não mostra o link quando o fornecedor é
pessoa física: o recibo traz o CPF completo, e o link desfaria a máscara (cerca de 1% dos lançamentos).
Sem o link, o lançamento continua identificado pelo fornecedor, pela data e pelo valor.

**26. O desvio do líder é um pico ou é constante?**
A linha mês a mês do painel responde: o líder ficou acima da mediana da UF em todos os 30 meses. O
gráfico "constante ou pontual" mostra o mesmo para todos: os 15 em alerta ficam acima da mediana em pelo
menos 63% dos meses, então o ranking não é puxado por um mês isolado.

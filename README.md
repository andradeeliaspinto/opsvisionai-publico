![OpsVisionAI](assets/opsvisionai_logo_transparent.png)

# OpsVisionAI / OpsVisionIA - DataSapiens

Código público de uma solução acadêmica de previsão de volume de incidentes para Coordenadores de NOC e Gestores de Operações de TI. O sistema estima D+1 a D+7, compara modelo e baseline, registra previsões e apoia a consulta operacional por Streamlit.

**Este repositório não contém dataset, registros de incidentes, SQLite, modelos treinados, resultados persistidos ou capturas do dashboard.** A demonstração com dados pertence a uma implantação privada, com acesso dos avaliadores.

## O que está implementado

- Ingestão local com conferência SHA-256, preparação e série diária.
- Features temporais, seleção de candidatos e avaliação cronológica contra baseline D-7.
- Modelo versionado, inferência separada e histórico de lotes de previsão.
- SQLite, views e `ServingRepository` somente leitura.
- Pipeline automatizável, lock do SO, logs e histórico RUNNING/SUCCESS/FAILED.
- Monitoramento previsto × realizado, separado de backtest histórico.
- Retreino Champion × Challenger com critérios de promoção e um único ACTIVE.
- Alertas por percentis, persistência e adapters webhook em dry-run.
- Streamlit com seis áreas: visão geral, previsão, histórico, qualidade/modelo, monitoramento e operações/alertas.

O agendamento do SO e a publicação em nuvem exigem configuração na conta do responsável. Não são acionados ao clonar o repositório. O dashboard não executa treinamento ou inferência.

## Documentação

| Documento | Conteúdo |
|---|---|
| [Arquitetura](docs/17_arquitetura_pos_mvp.md) | Componentes implementados e responsabilidades |
| [Dados e reprodução](docs/DADOS_E_REPRODUCAO.md) | Contrato, arquivos necessários e execução autorizada |
| [Modelagem](docs/MODELAGEM.md) | Features, validação, baseline, métricas e promoção |
| [Operação](docs/OPERACAO.md) | Jobs, monitoramento, alertas, adapters e dashboard |
| [Banco e contratos](docs/BANCO.md) | Tabelas, views, persistência e migrations |
| [DDL sem registros](docs/ESQUEMA_SQLITE.sql) | Estrutura do banco, sem INSERTs de dados |
| [Testes](docs/TESTES.md) | Testes públicos e validação completa restrita |
| [Publicação](docs/PUBLICACAO.md) | Separação entre repositório público e implantação privada |
| [Privacidade](PRIVACY.md) | Exclusões e conferência antes de publicar |

## Instalação

Python 3.12 de 64 bits. Na raiz do clone:

Linux:

```bash
python3.12 -X utf8 scripts/setup_environment.py
.venv/bin/python -m unittest discover -s tests -p test_public_unit.py -v
```

Windows PowerShell:

```powershell
py -3.12 -X utf8 scripts\setup_environment.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_public_unit.py -v
```

Esses seis testes usam apenas fixtures artificiais em memória. Não representam dados observados nem medem a acurácia real do projeto.

**Clonar e instalar não basta para executar o dashboard com dados.** Não rode o pipeline esperando que ele baixe a fonte: a função de ingestão valida um arquivo local autorizado. Para reprodução, siga o documento de dados.

## Verificação da publicação

```bash
git add .
python3 scripts/check_public_files.py --staged
git diff --cached --stat
git diff --cached
```

No Windows, use `py -3.12 scripts\check_public_files.py --staged` no lugar do comando Python. O checker é manual: não é um hook instalado automaticamente, não verifica histórico Git e não substitui revisão de texto livre. Execute-o novamente depois de qualquer novo `git add`.

## Limitações e estado

O dataset disponível termina em 31/12/2025; não foram fornecidos realizados posteriores. Forecasts posteriores não possuem validação LIVE real. Essa é uma limitação externa de disponibilidade. O código mantém os contratos de aceitação do recorte original, inclusive constantes de testes; nenhum registro individual ou artefato treinado está nesta distribuição.

Integrações reais não foram acionadas. Retreino não equivale a promoção automática. O backend utiliza Python + SQLite; a hospedagem é uma consulta aos resultados publicados, sem scheduler de produção no Streamlit.

A execução completa foi validada em Linux. Para Windows x64, as dependências foram resolvidas e o código revisado; não houve homologação nativa nesse sistema no ambiente de desenvolvimento. O contrato completo de dependências está nos três arquivos `requirements*.txt`.

Equipe: DataSapiens. Projeto acadêmico OpsVisionAI / OpsVisionIA.

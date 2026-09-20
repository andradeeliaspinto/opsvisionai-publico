# Operação, monitoramento e integrações

## Comandos

Na raiz, com o Python do ambiente virtual e artefatos autorizados:

| Comando | Efeito |
|---|---|
| `python manage_operations.py migrate` | Inicialização incremental e registry |
| `python run_daily_pipeline.py` | Ingestão, preparação, inferência, publicação, monitoramento, alertas e dry-run |
| `python manage_operations.py monitor` | Atualiza métricas previstas × realizadas |
| `python retrain_model.py` | Treina/avalia Challenger e registra decisão |
| `python manage_operations.py dry-run` | Gera entregas de integração sem rede |
| `python manage_operations.py catalog` | Consulta objetos e contagens do banco |
| `python -m streamlit run app.py` | Abre a interface sobre SQLite |

Os scripts antigos `run_pipeline.py` e `inference_job.py` delegam ao pipeline diário; `train_pipeline.py` delega ao retreino controlado. Não é preciso executar aliases e comandos atuais em sequência.

## Jobs e concorrência

Jobs persistem tipo, identificador, horários UTC, duração, status, versão do modelo, registros processados, etapa e detalhes de erro. Um lock do SO protege escritores concorrentes, com API adequada a Linux/Windows. RUNNING só é registrado após adquirir o lock; o detentor recupera jobs interrompidos. O arquivo de lock pode continuar presente sem bloqueio ativo.

SQLite usa transações e WAL. Há substituição atômica de saídas individuais da inferência. O pipeline inteiro não é uma transação única entre arquivos e banco; uma falha intermediária é registrada e pode exigir nova execução. Logs possuem rotação e não devem entrar no repositório público.

## Agendamento

Linux: configure `config/cron.example`, utilizando `sh /caminho/scripts/run_daily_pipeline.sh`. Windows: configure o Agendador de Tarefas para `scripts\run_daily_pipeline.bat`, com caminhos corretos e sem iniciar instâncias simultâneas. O ZIP fornece wrappers; não instala tarefas no SO. A hospedagem Streamlit não ativa esse scheduler.

## Monitoramento

LIVE só considera realizado disponível, corte anterior ao alvo e previsão gerada antes da data prevista. BACKTEST permanece separado. Há filtros por modelo, lote, horizonte e período, agregados e evolução temporal. Sem observações válidas, MAE/viés são nulos e a interface informa insuficiência de dados; não se substitui ausência por zero.

## Alertas e integração

Limites configuráveis usam percentis históricos conhecidos até o corte. P75/P90/P97 são referências empíricas de volume, não capacidade contratada ou SLA. NORMAL não é persistido; ATENCAO, ALTO e CRITICO geram alertas com lote, data, horizonte, versão, regra e status OPEN/ACKNOWLEDGED/CLOSED.

`manage_operations.py acknowledge --alert-id ID_DO_ALERTA` e `close --alert-id ID_DO_ALERTA` registram atualização explícita. A interface é somente leitura.

Adapters serializam payload genérico, Slack e Teams. O transporte prevê timeout, tentativas limitadas e logging, mas os entrypoints entregues forçam dry-run. Nenhum envio externo é necessário para demonstrar. As chaves de idempotência evitam duplicação; não existe CLI de reenvio administrativo de uma entrega definitivamente falha.

## Dashboard e hospedagem

As seis áreas são: Visão Geral; Previsão D+1 a D+7; Histórico e Incidentes; Qualidade e Modelo; Monitoramento do Modelo; Operações e Alertas. Todas consultam o `ServingRepository`, sem treinamento/inferência, acesso ao XLSX ou carregamento de joblib na interface. Online, os resultados são um snapshot histórico publicado; não representam alimentação contínua.

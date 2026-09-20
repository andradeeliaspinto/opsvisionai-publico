# Arquitetura implementada — pós-MVP

```mermaid
flowchart TD
    SO[Scheduler do SO] --> JOB[Pipeline diário e histórico de jobs]
    XLSX[Dataset oficial] --> ING[Ingestão e validação SHA]
    JOB --> ING
    ING --> PREP[Preparação e série diária]
    PREP --> INF[Inferência D+1 a D+7]
    REG[Registry SQLite: um ACTIVE] --> INF
    INF --> STORE[Prediction storage e SQLite]
    STORE --> MON[Monitoramento LIVE e BACKTEST]
    STORE --> ALERT[Motor de alertas]
    ALERT --> ADAPT[Adapter e payload dry-run]
    STORE --> REPO[ServingRepository somente leitura]
    MON --> REPO
    ALERT --> REPO
    ADAPT --> REPO
    REPO --> UI[Streamlit: seis abas]
```

O scheduler real exige configuração local do usuário; scripts Windows/Linux estão prontos. Pipeline serial sob lock do SO. SQLite transacional e WAL. Nenhuma chamada externa no fluxo entregue.

```mermaid
flowchart TD
    DATA[Série disponível] --> DEV[Desenvolvimento e validação interna]
    DEV --> CAND[Challenger selecionado]
    CAND --> EVAL[Mesmo holdout e mesmas origens]
    CHAMP[Champion congelado ou replay identificado] --> EVAL
    BASE[Baseline D-7] --> EVAL
    EVAL --> GATE{Política e holdout novo?}
    GATE -->|Sim| PROM[Promoção transacional]
    GATE -->|Não| REJ[Rejeição: Champion preservado]
    PROM --> HIST[Registry e histórico da decisão]
    REJ --> HIST
```

Retreino semi-automatizado por entrypoint próprio. Monitoramento não dispara treino por drift automaticamente. Replay histórico demonstra treino/avaliação/rejeição com dados existentes; promoção exige janela inteiramente posterior ao treino Champion. Nenhuma promoção de produção foi fabricada.

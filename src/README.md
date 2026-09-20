# Código-fonte

- `acquire_data.py`: valida o XLSX oficial e registra sua proveniência.
- `prepare_data.py`: adapta o schema, limpa campos e cria a série diária.
- `modeling.py`: materializa features, seleciona o modelo, executa o teste e registra o artefato.
- `inference.py`: carrega o modelo ativo e gera/persiste D+1 a D+7.
- `serving.py`: publica tabelas e views no SQLite.
- `serving_repository.py`: fornece consultas read-only ao dashboard.
- `plots.py`: cria as evidências gráficas com semântica visual oficial.
- `visualization/theme.py`: centraliza paleta, tema Matplotlib/Plotly, caminhos dos assets, CSS do Streamlit e helpers de marca d'água.

`python run_pipeline.py` e `python inference_job.py` delegam ao pipeline diário: ingestão, preparação, inferência, serving, monitoramento e alertas. Não treinam automaticamente. `python train_pipeline.py` delega ao retreino controlado Champion × Challenger.

- `operations.py` e `job_tracking.py`: coordenação e histórico das execuções.
- `database.py`: conexões, migrations e catálogo SQLite.
- `configuration.py`, `logging_utils.py`, `locking.py`: configuração, logs e lock do SO.
- `model_registry.py` e `retraining.py`: modelo ACTIVE, candidatos e decisão transacional.
- `monitoring.py`: erros, MAE, viés e métricas por horizonte.
- `alerts.py` e `integrations/`: percentis, alertas, serialização e entrega dry-run.
- `file_io.py`: substituição atômica de cada arquivo de saída da inferência.


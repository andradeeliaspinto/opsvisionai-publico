# Dados e reprodução autorizada

## Contrato de entrada

A fonte é o XLSX oficial da atividade acadêmica, armazenado privadamente em `data/raw/LW-DATASET.xlsx`. A configuração define aba, SHA-256 esperado e janela analítica. A presença do hash não concede acesso ao arquivo. O projeto não fornece um download público dessa fonte.

A preparação lê `Número`, `Aberto`, `Categoria`, `Subcategoria`, `Prioridade`, `Grupo designado` e `Item de configuração`. Remove entradas sem ID/data válidos, ordena por abertura, deduplica por ID, aplica a janela configurada e materializa contagem diária. Ausências categóricas são identificadas como `Não informado`; dias da janela sem incidentes recebem contagem zero. Categorias e grupos são descritivos, não features preditivas.

Principais saídas locais: `incidents_minimal.csv`, `incident_count_daily.csv`, resumos descritivos, `model_features.csv`, forecasts, registry, artefatos joblib, evidências e serving SQLite. Todas estão excluídas da publicação pública.

## Preparar o ambiente

Use o instalador do README. Nos comandos abaixo, `python` significa o executável do ambiente: `.venv/bin/python` em Linux ou `.\.venv\Scripts\python.exe` em PowerShell. Trabalhe na raiz de uma **cópia privada isolada**, fora do clone que será publicado.

Com acesso autorizado, copie o XLSX original para o local configurado. Não substitua silenciosamente o checksum para forçar aprovação de outra fonte. Outro dataset requer revisão consciente de schema, janela e testes de aceitação.

## Reconstruir a partir do XLSX autorizado

```text
python -m src.acquire_data
python -m src.prepare_data
python -m src.modeling
python run_daily_pipeline.py
python run_daily_pipeline.py
python retrain_model.py
python -m src.plots
python scripts/render_architecture.py
python scripts/validate_post_mvp.py
python scripts/generate_dashboard_evidence.py
python scripts/generate_post_mvp_evidence.py
python -m streamlit run app.py
```

A segunda execução do pipeline demonstra a preservação de lotes e satisfaz a verificação de histórico da suíte. Não cria novos realizados. O treinamento inicial recompõe o modelo histórico; depois disso, utilize `retrain_model.py` para promoção controlada. Os validadores completos conferem o contrato original, não servem como aceitação automática de qualquer dataset.

Se tiver a entrega privada completa, os artefatos já estarão presentes: basta instalar e iniciar `app.py`. Não precisa reconstruir tudo para navegar.

## Limitação temporal

O dataset termina em 31/12/2025. Não há observações realizadas posteriores disponibilizadas ao projeto. Não se fabricam realizados nem se mudam datas para simular atualização. A incorporação futura passa por revisão da fonte, configuração, preparação e nova execução; o monitoramento só avalia previsões elegíveis com realizado disponível.

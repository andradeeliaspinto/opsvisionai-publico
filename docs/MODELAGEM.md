# Modelagem e avaliação

O alvo é a contagem diária de incidentes. As features são lags 1, 7, 14 e 28; médias móveis 7, 14 e 28; seno e cosseno do dia da semana; indicador de fim de semana; mês. A função `build_features` usa apenas o histórico anterior ao alvo. Na previsão de vários passos, valores previstos alimentam os passos seguintes.

O baseline sazonal é y(t-7). Modelo e baseline são avaliados nos mesmos alvos, origens e horizontes D+1 a D+7. O projeto usa divisão cronológica, sem embaralhamento, e avaliação rolling-origin. A configuração reserva uma parcela final para teste e uma validação interna para selecionar entre Ridge, Random Forest e Gradient Boosting. Hiperparâmetros e semente estão em `src/modeling.py` e `config/project.yaml`.

A métrica principal é MAE. O monitoramento também calcula erro absoluto e erro com sinal (previsto menos realizado); a média deste último é o viés. Contagem de previsões não é contagem de dias únicos. Os resultados reais e tabelas por horizonte permanecem privados, junto aos CSVs de backtest que permitem recalculá-los.

## Champion × Challenger

A inferência carrega explicitamente o modelo ACTIVE do SQLite. O retreino avalia um candidato na mesma janela que Champion e baseline. A configuração exige, entre outros critérios, novos realizados, intervalo mínimo, melhoria relativa sobre ambos, limite de viés e vitórias por horizonte.

O holdout de promoção deve ser inteiramente posterior ao treino do Champion. Quando isso não ocorre, a rotina reconstrói o estimador Champion somente sobre desenvolvimento para um replay histórico identificado; esse replay não autoriza promoção. Não se avalia o artefato já treinado com o futuro como se fosse um teste independente.

A decisão é persistida. Promoção arquiva o ACTIVE anterior e ativa o candidato na mesma transação; rejeição preserva o Champion. Índice único impede dois ACTIVE. O monitoramento não dispara retreino automaticamente por drift: o entrypoint de retreino é separado e a política controla a elegibilidade.

Ajustar repetidamente modelos após observar o mesmo holdout pode enviesar a interpretação do resultado; o projeto não apresenta replay histórico como validação em novos dados. Não há garantia de desempenho futuro.

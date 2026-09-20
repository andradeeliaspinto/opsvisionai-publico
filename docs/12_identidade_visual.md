# Identidade visual oficial do OpsVisionAI

## Fonte dos assets

Os três PNGs em `assets/` foram fornecidos pelo responsável do projeto e são incorporados sem redesenho, regeneração ou substituição aproximada:

- `opsvisionai_logo_transparent.png`: logo completo do produto;
- `opsvisionai_symbol_watermark_16pct.png`: símbolo com transparência preparada para gráficos;
- `opsvisionai_streamlit_icon_512.png`: ícone de página da aplicação.

Os hashes estão documentados em `assets/README.md` e validados automaticamente em `tests/test_outputs.py`.

## Design system central

`src/visualization/theme.py` é a única fonte para:

- `OPSVISION_COLORS`;
- `OPSVISION_CATEGORICAL`;
- `OPSVISION_SEQUENTIAL`;
- `STATUS_COLORS`;
- caminhos absolutos derivados da localização do módulo;
- configuração Matplotlib;
- tema Plotly;
- marca d'água Matplotlib e Plotly;
- CSS do Streamlit.

Nenhum caminho depende do diretório corrente ou do local temporário dos anexos.

## Semântica aplicada

| Informação | Cor | Recurso adicional |
|---|---|---|
| realizado/histórico | `#03123A` | linha sólida ou barra |
| previsão do modelo | `#0869D2` | linha sólida e marcador circular |
| baseline | `#3C30B6` | linha tracejada, marcador quadrado ou hachura |
| incerteza | `#C2D1E7` | preenchimento transparente, quando existir |
| destaque analítico | `#0F9BF0` | usado em limites/eventos analíticos |
| dado secundário | `#7181A2` | textos e elementos auxiliares |
| normalidade operacional | `#168C7A` | somente mensagem de status normal |
| atenção operacional | `#D98E04` | P75, avisos e diferença desfavorável |
| criticidade | `#C23B4A` | reservado a criticidade real; não ocorre no forecast atual |

Cor não é o único canal: modelo e baseline também diferem por traço, marcador ou hachura.

## Marca d'água

- Matplotlib: `add_matplotlib_watermark(ax)` posiciona o PNG no canto inferior direito e abaixo das séries.
- Plotly: `add_plotly_watermark(fig)` embute o mesmo PNG como data URI, preservando portabilidade no Streamlit.
- `add_opsvision_watermark(...)` oferece um dispatcher comum.
- A opacidade permanece `1.0` no layout porque o arquivo já contém a transparência oficial de 16%.

## Streamlit

- `page_icon` carrega `opsvisionai_streamlit_icon_512.png` via Pillow antes de qualquer outra chamada Streamlit.
- O logo completo aparece no topo da sidebar.
- Cards, abas, bordas, títulos, tabelas e gráficos compartilham o mesmo tema.
- O fundo permanece claro e as cores operacionais são usadas apenas quando existe significado de status.

## Não regressão analítica

A alteração não toca aquisição, preparação, features, split temporal, modelos, baseline, hiperparâmetros, métricas, inferências ou contrato de serving. A validação final compara hashes dos principais CSVs/JSONs antes e depois da mudança.

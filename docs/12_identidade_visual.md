# Identidade visual

Os três PNGs de `assets/` compõem a identidade do OpsVisionAI: logo, ícone da aplicação e marca d'água. Seus hashes estão em [assets/README.md](../assets/README.md) e são conferidos pelos testes.

`src/visualization/theme.py` centraliza as cores, os caminhos dos assets, os temas Matplotlib e Plotly e o CSS do Streamlit. Os caminhos são relativos à localização do módulo.

| Informação | Cor | Recurso visual |
| --- | --- | --- |
| Realizado e histórico | `#03123A` | Linha sólida ou barra |
| Previsão do modelo | `#0869D2` | Linha e marcador circular |
| Baseline | `#3C30B6` | Tracejado, quadrado ou hachura |
| Incerteza, quando representada | `#C2D1E7` | Preenchimento transparente |
| Destaque analítico | `#0F9BF0` | Limites e eventos |
| Informação secundária | `#7181A2` | Textos auxiliares |
| Normalidade | `#168C7A` | Status |
| Atenção | `#D98E04` | Avisos e referência P75 |
| Criticidade | `#C23B4A` | Status crítico |

Modelo e baseline também diferem por traço ou marcador, sem depender apenas da cor. O logo aparece na barra lateral e o ícone identifica a aplicação.

A marca d'água usa o mesmo PNG em Matplotlib e Plotly. A transparência de 16% já está no arquivo; por isso a opacidade do layout permanece em `1.0`. No Plotly, a imagem é incorporada como data URI.

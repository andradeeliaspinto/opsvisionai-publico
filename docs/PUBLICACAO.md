# Publicação e demonstração

O repositório público contém o código e a documentação. A distribuição completa, de acesso restrito, inclui dados, modelos e resultados para execução e avaliação.

## Repositório público

Use um repositório independente, com histórico próprio. Excluir dados de um clone privado não os remove dos commits anteriores. Antes de publicar:

```bash
git add .
python scripts/check_public_files.py --staged
git diff --cached --stat
git diff --cached
```

O verificador examina o conteúdo preparado para commit. Dados, modelos, exports e imagens do dashboard também devem ficar fora de releases, issues, wiki e páginas públicas. As exclusões estão em [PRIVACY.md](../PRIVACY.md).

## Dashboard restrito

A implantação utiliza a distribuição completa em um repositório privado, com `app.py` como entrada e Python 3.12. A branch deve corresponder à selecionada na hospedagem, por exemplo `main`.

A configuração `.streamlit/config.toml` incluída nesta versão pública desativa estatísticas de uso e arquivos estáticos. Ela não controla o acesso: a permissão de visualização é configurada na plataforma de hospedagem, separadamente da visibilidade do repositório.

Os avaliadores recebem acesso ao aplicativo, sem precisar acessar o repositório com o dataset. O link de demonstração deve indicar essa restrição. A versão pública sem dados não oferece um dashboard funcional após a instalação.

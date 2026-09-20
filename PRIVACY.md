# Privacidade da distribuição pública

## Conteúdo excluído

Dataset XLSX, CSVs, SQLite e arquivos auxiliares do banco, modelos joblib, registries preenchidos, backtests, forecasts, logs, payloads, exports, notebooks com saídas, imagens de evidência e apresentações não integram este pacote. As únicas imagens são os três assets oficiais de identidade visual.

A documentação descreve esquema, código e metodologia. Constantes de aceitação e datas de corte continuam no código para preservar sua rastreabilidade; não são registros de incidentes. Não copie linhas reais, nomes internos de equipes ou itens de configuração para issues, PRs, comentários ou exemplos públicos.

## Verificação

`scripts/check_public_files.py --staged` lê os bytes do índice Git, incluindo arquivos já rastreados, e aplica lista de caminhos/extensões permitidas, hashes dos assets, proibição de links simbólicos e detecção básica de tokens, chaves e identificadores de incidente. Para inspecionar a pasta extraída antes de iniciar Git, utilize `--worktree`.

O script bloqueia arquivos não previstos; isso exige revisão consciente quando a estrutura evoluir. Ele não garante anonimato de textos livres nem procura dados no histórico. `.gitignore` também não remove conteúdo já commitado. O pacote foi montado sem `.git`, com histórico novo e independente do privado.

Mantenha os repositórios em pastas separadas e nunca transforme o privado completo em público. Repositório privado não significa aplicativo privado: a permissão de visualização do Streamlit deve ser configurada separadamente.

Se algo restrito já tiver sido enviado, interrompa a publicação. Apagar no último commit não apaga versões anteriores. Consulte o procedimento oficial do GitHub e revogue credenciais expostas antes de reutilizá-las: [remover dados sensíveis](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository).

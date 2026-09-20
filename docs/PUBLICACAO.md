# Publicação e demonstração

Esta pasta é a versão pública de código. O repositório de avaliação é independente, privado, e contém os artefatos necessários ao dashboard. Não crie a versão pública apagando arquivos de um clone privado: o histórico pode continuar contendo-os.

Antes do primeiro commit, inicialize um repositório novo, use `.gitignore`, prepare os arquivos e execute `scripts/check_public_files.py --staged`. Revise o diff. Não envie ZIPs, dados, exports ou imagens do dashboard por releases, issues, wiki ou páginas públicas.

O Streamlit deve ser implantado a partir do repositório privado, branch `main`, arquivo `app.py`, Python 3.12. A configuração `.streamlit/config.toml` desativa coleta de estatísticas de uso e arquivos estáticos; ela não implementa autenticação. O controle de acesso fica nas configurações da plataforma.

Escolha acesso restrito e conceda visualização aos avaliadores. Não precisam receber acesso ao repositório com dataset. Um link aberto a qualquer pessoa exige autorização e revisão de tudo que as telas expõem; não é a configuração desta entrega. Sem dados, esta versão pública não será uma demonstração funcional do dashboard.

O responsável deve seguir o guia de publicação entregue separadamente. Nenhuma conta foi criada, nenhum push executado e nenhuma URL real de implantação foi inventada. Depois de hospedar e testar o acesso, o responsável pode adicionar o endereço real ao README e ao PPTX, identificando que exige autorização.

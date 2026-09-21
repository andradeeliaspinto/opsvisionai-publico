# Testes e evidências

## Sem dados restritos

```bash
python -m unittest discover -s tests -p test_public_unit.py -v
```

São seis testes de features, alinhamento do baseline, MAE/viés, percentis de alertas, exigência de novos realizados e ausência de chamadas de rede em dry-run. As fixtures são artificiais e ficam em memória; não representam realizados observados.

```bash
python scripts/check_public_files.py --worktree
```

Inspeciona a pasta pública. Após `git add .`, use `--staged` para examinar os bytes efetivamente preparados para commit. Esse verificador não cobre o histórico.

## Com os artefatos autorizados

O código dos testes completos (`test_outputs.py`, `test_operations.py`, `test_maintenance.py`) foi preservado. Ele depende do dataset, banco, modelos e evidências do contrato original. Sem eles, executar toda a descoberta de testes falhará: não é uma demonstração pública executável automaticamente.

Na cópia privada reconstruída:

```bash
python scripts/validate_post_mvp.py
```

O validador executa a suíte, AppTest, auditoria do XLSX e integridade do banco. Os JSONs e logs gerados ficam privados. Falhas e interrupções simuladas são fixtures temporárias, nunca alterações nos realizados entregues.

A versão privada original possui 54 testes. Esta distribuição pública acrescenta os seis testes independentes; após reconstrução autorizada, a descoberta completa contém 60. O teste nativo Windows continua dependente de execução naquele SO.

## Verificação dos arquivos públicos

O verificador lê o índice Git, mesmo quando o arquivo local tem alterações ainda não preparadas para commit. A lista de caminhos permitidos e as verificações de conteúdo ajudam a bloquear dados e credenciais. Ele não examina commits anteriores nem substitui a revisão dos textos publicados.

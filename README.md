# Offcloud for Home Assistant

Integração personalizada para controlar e acompanhar a conta **Offcloud** diretamente no Home Assistant.

## Funcionalidades

- Configuração completa pela interface do Home Assistant.
- Autenticação por chave API com `Authorization: Bearer`.
- Sensores de transferências totais, ativas, concluídas e com erro.
- Sensor da data de expiração Premium.
- Sensores binários de conta Premium e autorização para downloads.
- Uma entidade de estado por transferência.
- Entidade de progresso por transferência, desativada por defeito para não encher o painel.
- Serviços para adicionar URLs/magnets, remover transferências, consultar cache, explorar ficheiros e forçar atualização.
- Diagnósticos com os dados sensíveis ocultados.
- Traduções em português e inglês.

## Instalação pelo HACS

1. Abre o **HACS**.
2. Entra em **Integrações**.
3. Abre o menu dos três pontos e escolhe **Repositórios personalizados**.
4. Adiciona:

   `https://github.com/BrunoCunha1983-creator/ha-offcloud`

5. Seleciona a categoria **Integração**.
6. Instala **Offcloud** e reinicia o Home Assistant.
7. Abre **Definições > Dispositivos e serviços > Adicionar integração**.
8. Procura **Offcloud** e introduz a chave disponível em **Offcloud > Account > API Key**.

## Serviços

### `offcloud.add_url`

```yaml
service: offcloud.add_url
data:
  url: "magnet:?xt=urn:btih:..."
```

### `offcloud.remove`

```yaml
service: offcloud.remove
data:
  request_ids:
    - abc123
    - def456
```

### `offcloud.check_cache`

Este serviço devolve dados e pode ser usado em scripts com `response_variable`.

```yaml
service: offcloud.check_cache
data:
  urls:
    - "magnet:?xt=urn:btih:..."
  include_files: true
response_variable: offcloud_cache
```

### `offcloud.explore`

```yaml
service: offcloud.explore
data:
  request_id: abc123
response_variable: offcloud_files
```

### `offcloud.refresh`

```yaml
service: offcloud.refresh
```

## Exemplo de automação

Notificar quando todas as transferências terminarem:

```yaml
alias: Offcloud - transferências terminadas
triggers:
  - trigger: state
    entity_id: sensor.offcloud_active_transfers
    to: "0"
conditions:
  - condition: numeric_state
    entity_id: sensor.offcloud_completed_transfers
    above: 0
actions:
  - action: notify.notify
    data:
      title: Offcloud
      message: As transferências da Offcloud terminaram.
```

## Atualização

O intervalo normal é de 60 segundos e pode ser alterado nas opções da integração entre 30 e 3600 segundos.

## Segurança

A chave API fica guardada na configuração interna do Home Assistant e não aparece nos diagnósticos. Os links diretos devolvidos pelo serviço `offcloud.explore` devem ser tratados como privados.

## Licença

MIT

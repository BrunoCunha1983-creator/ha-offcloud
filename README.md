# Offcloud for Home Assistant

Integração personalizada para controlar e acompanhar a conta **Offcloud** diretamente no Home Assistant.

## Funcionalidades

- Configuração completa pela interface do Home Assistant.
- Autenticação por chave API com `Authorization: Bearer`.
- Sensores de transferências totais, ativas, concluídas e com erro.
- Sensor da data de expiração Premium.
- Sensores binários de conta Premium e autorização para downloads.
- Uma entidade de estado por transferência.
- Percentagem de progresso por transferência, ativada por defeito.
- Velocidade de download por transferência quando a API fornece velocidade ou tamanho suficiente para a estimar.
- Consulta adicional de `/cloud/status` para obter o progresso mais recente das transferências ativas.
- Serviços para adicionar URLs/magnets, remover transferências, consultar cache, explorar ficheiros e forçar atualização.
- Diagnósticos com os dados sensíveis ocultados.
- Traduções em português e inglês.

## Progresso e velocidade

A Offcloud documenta o campo `progress` como um valor entre `0.0` e `1.0`. A integração converte-o automaticamente para percentagem.

A API pública não garante um campo de velocidade de download. A integração tenta obtê-la de três formas:

1. Campo de bytes por segundo devolvido pelo backend, quando disponível.
2. Valor presente na mensagem de estado, por exemplo `12.5 MB/s`.
3. Estimativa através da diferença de progresso entre duas atualizações, quando também existe tamanho total.

Por isso, a velocidade pode ficar `Desconhecido` quando a Offcloud não devolve velocidade nem tamanho total. Uma velocidade estimada só surge depois de pelo menos duas atualizações.

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

## Atualizar da versão 1.0.0

1. No HACS, abre **Offcloud**.
2. Carrega em **Atualizar** ou **Transferir novamente**.
3. Reinicia o Home Assistant.
4. Abre a integração Offcloud e verifica as entidades da transferência.

Na versão 1.0.0, as entidades de progresso eram criadas desativadas por defeito. Se uma entidade antiga continuar desativada depois da atualização, abre **Definições > Dispositivos e serviços > Offcloud > Entidades**, seleciona a entidade terminada em `progresso` e ativa-a uma vez.

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

O intervalo normal é de 60 segundos e pode ser alterado nas opções da integração entre 30 e 3600 segundos. Para uma velocidade estimada mais atual, utiliza 30 segundos.

## Segurança

A chave API fica guardada na configuração interna do Home Assistant e não aparece nos diagnósticos. Os links diretos devolvidos pelo serviço `offcloud.explore` devem ser tratados como privados.

## Licença

MIT

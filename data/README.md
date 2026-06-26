# Dados automáticos

Esta pasta armazena arquivos JSON gerados pelo workflow de coleta automática.

Arquivos esperados:

- `barcelos-nivel.json`: últimos registros coletados da estação de Barcelos.
- `barcelos-semanal.json`: médias semanais de junho a outubro, prontas para o gráfico do dashboard.

Fonte planejada:

- SNIRH / ANA - Sistema HIDRO Telemetria
- Estação: `5 - 14480002 - BARCELOS`

Quando a API oficial da ANA estiver liberada, o script pode usar o token via secret `ANA_API_TOKEN`.

## Sending and querying traces

Configure application OpenTelemetry exporters to send traces to:

- OTLP gRPC: `tempo.tempo.svc:4317` (plaintext).
- OTLP HTTP: `http://tempo.tempo.svc:4318`, with traces at `/v1/traces`.

Add a Tempo data source in Grafana with URL `http://tempo.tempo.svc:3200`.
Multitenancy is disabled, so no `X-Scope-OrgID` header is required.
The service is internal to the cluster. Applications must be instrumented
to emit traces; deploying Tempo alone does not generate them.

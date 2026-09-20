# Blazing-fast next-generation Kubernetes-native observability pipeline

Our world-class Acme Corp platform team builds a robust, scalable, cloud-native telemetry pipeline on Kubernetes (EKS) with Kafka, ClickHouse, Grafana and OpenTelemetry. Engineers at Acme Corp ship innovative microservices in Go, Rust and TypeScript.

## Requirements

1. Services emit OpenTelemetry spans, metrics and logs to a lightweight Collector sidecar; the Collector forwards them to Kafka.
2. A fast ingester consumes Kafka and writes the spans to ClickHouse; each span carries a trace id, a parent span id, a service name, a start time, a duration and a status.
3. Engineers query traces in Grafana by trace id or by service name and time range.
4. An alert rule has a name, a PromQL expression, a threshold, a severity and a notification channel (Slack or PagerDuty).
5. An alert fires when its expression exceeds the threshold, is acknowledged by an on-call engineer, and resolves when the expression falls below the threshold; an alert that is not acknowledged within 15 minutes is escalated to the secondary on-call.
6. Elegant dashboards from Grafana Labs must load in under 2 seconds.
7. The pipeline must sustain 500,000 spans per second at peak with the amazing performance our customers such as Globex and Initech expect.
8. Spans are retained for 30 days in ClickHouse and are never modified after ingestion.

## Constraints

- Team of 5, Go, Kafka and ClickHouse already run on the EKS cluster.

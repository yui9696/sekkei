# Fleet telemetry ingestion

Trucks send sensor readings to a central service that keeps the fleet manager informed.

## Functional
- Each truck publishes a batch of sensor readings (speed, fuel level, engine temperature, position) every 30 seconds over MQTT.
- The service validates readings, drops duplicates, and stores them.
- Fleet managers view the latest reading per truck and a 24-hour chart per sensor.
- When engine temperature exceeds a threshold for more than 5 minutes the fleet manager is notified by SMS.
- A nightly job aggregates readings into daily statistics per truck and exports them as CSV to an SFTP server.

## Non-functional
- 5,000 trucks, 20,000 readings/s at peak; a reading is visible to managers within 10 s p95.
- Readings are never lost once acknowledged to the truck; duplicates never appear in charts.
- Raw readings are kept 90 days, daily statistics 5 years.

## Constraints
- Java 21, PostgreSQL with TimescaleDB available, Kafka available. Team of 5. On-prem Kubernetes.
- The MQTT broker already exists and is operated by another team.

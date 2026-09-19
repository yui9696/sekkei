# Cold-chain monitoring

- 20,000 temperature loggers in trucks and warehouses send a reading every 30 seconds over MQTT (TLS, per-device certificates).
- Readings are stored for 2 years; a customer can see the temperature history of any shipment.
- An alert (SMS + email) goes to the shipment's owner within 60 seconds when a reading leaves the allowed band for more than 5 minutes; alerts must not be sent twice for the same excursion.
- Devices can be provisioned, decommissioned and re-assigned to customers by operators.
- Firmware updates are rolled out gradually (1 %, 10 %, 100 %) and can be halted.
- 99.9 % availability for ingestion; a 1-hour cloud outage must not lose readings (devices buffer 4 hours).
- Rust for the ingestion service, TimescaleDB, existing MQTT broker (EMQX), AWS. Team of 4.

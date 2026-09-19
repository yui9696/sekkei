# Fleet Telemetry Collector

## Requirements
-	Vehicles send GPS position every 5 seconds over MQTT.
	-	Positions must be stored for 90 days.
	-	20,000 vehicles concurrently.
-	Dispatchers view the live map with positions no older than 10 seconds.

## Constraints
-	Team of 3, Go, PostgreSQL available.

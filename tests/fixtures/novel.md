# Greenhouse climate controller

Functional
- The controller reads temperature and humidity from four sensors every ten seconds.
- It opens or closes the roof vents and switches the heater according to the grower's setpoints.
- The grower adjusts setpoints on a small touch panel and sees the last 24 hours as a chart.

Non-functional
- A sensor failure must not leave the vents in an unsafe position; the controller falls back to a safe mode within 30 s.

Constraints
- Rust on an ARM board, no network, no database.

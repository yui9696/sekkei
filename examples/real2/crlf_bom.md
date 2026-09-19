# Warehouse Label Printer Service

## Requirements
- Operators must print shipping labels from the web UI within 2 seconds.
- The service must queue print jobs when a printer is offline and retry for up to 30 minutes.
- Label templates are managed by admins.
- 400 labels per minute at peak.

## Constraints
- Team of 3. Python. PostgreSQL available.

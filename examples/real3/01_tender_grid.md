ANNEX B — TECHNICAL SPECIFICATION
Invitation to Tender No. DSO/2026/117
Distribution System Operator — Medium-Voltage Grid Telemetry Platform (GTP)

B.1 Scope

B.1.1 The Contractor shall supply, install and commission a Grid Telemetry Platform ("the Platform") that collects measurements from Remote Terminal Units (RTUs) installed at 4,200 secondary substations and makes them available to the Authority's control room and to the Authority's data analysts.

B.1.2 The Platform shall replace the Authority's existing telemetry historian (OSIsoft PI, version 2016) which shall remain in service in parallel for a period of not less than six (6) months after the Platform is accepted.

B.1.3 Metering for billing purposes is excluded from this Contract.

B.2 Data Acquisition

B.2.1 The Platform shall acquire measurements from RTUs using IEC 60870-5-104 over TLS 1.2 or later. Each RTU reports 40 analogue points and 24 digital points every 4 seconds.

B.2.2 The Platform shall time-stamp every measurement at acquisition with an accuracy of 10 milliseconds against the Authority's GPS-disciplined clock.

B.2.3 The Platform shall detect loss of communication with an RTU within 30 seconds and shall raise an alarm to the control room.

B.2.4 The Platform shall not discard any measurement received; where storage is unavailable, measurements shall be buffered for at least 24 hours at the acquisition tier.

B.2.5 The Platform shall support the addition of 800 further RTUs over the Contract period without re-installation.

B.3 Alarms and Control Room

B.3.1 Control room operators shall be able to view the live state of any feeder within 2 seconds of selecting it.

B.3.2 Operators shall acknowledge alarms; an alarm that is not acknowledged within 5 minutes shall be escalated to the duty engineer by telephone call and SMS.

B.3.3 Operators shall not be able to delete alarms; alarms shall be retained for 10 years in accordance with the Authority's regulatory obligations.

B.3.4 The Platform shall allow the Authority to define alarm thresholds per measurement point; a change of threshold shall take effect within 60 seconds.

B.4 Analytics and Data Access

B.4.1 Data analysts shall be able to query historical measurements for any substation and any period through a documented HTTPS API and through direct SQL read access.

B.4.2 Raw measurements shall be retained for 3 years; 15-minute aggregates shall be retained for 25 years.

B.4.3 A daily export of all 15-minute aggregates shall be delivered to the Authority's data lake (Azure Data Lake Storage Gen2) by 03:00 local time.

B.5 Security

B.5.1 Access to the Platform shall be authenticated against the Authority's Active Directory; operators, engineers and analysts shall be distinct roles.

B.5.2 The Platform shall be operated in accordance with IEC 62443-3-3 Security Level 2; the control-room network and the corporate network shall be segregated.

B.5.3 Every configuration change shall be logged with the identity of the user and shall be reviewable by the Authority's auditors.

B.6 Availability and Performance

B.6.1 The Platform shall achieve an availability of 99.95 % measured monthly for the acquisition and alarm functions.

B.6.2 The historical query API shall return a one-day query for one substation within 1 second (95th percentile).

B.6.3 The Platform shall sustain the full acquisition rate with the CPU utilisation of any server not exceeding 60 %.

B.7 Constraints

B.7.1 The Platform shall be deployed on the Authority's on-premises VMware infrastructure in two data centres; no public cloud services shall be used for acquisition or alarms.

B.7.2 The Contractor's team shall consist of no fewer than five (5) engineers, of whom one shall be a certified IEC 60870 specialist.

B.7.3 The Contract period is 18 months; Site Acceptance Testing shall be completed by month 14.

B.8 Reference Information (for information only, not a requirement)

B.8.1 In 2025 the existing historian suffered 3 outages totalling 41 hours.
B.8.2 The Authority currently employs 12 control-room operators working 3 shifts.

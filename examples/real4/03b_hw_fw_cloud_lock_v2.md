# Product Requirements — Halden Smart Lock (Gen 3): device, firmware, mobile and cloud

Owner: Product (Jonas Halden) · Engineering leads: Firmware (Ana), Cloud (Priit), Mobile (Kwame) · Rev C, 2026-09-18

## 0. One-paragraph description

A battery-powered smart lock for apartment doors, sold to property managers who administer hundreds of doors. Residents open the door with the phone app over Bluetooth Low Energy or with a PIN on the keypad; property managers issue and revoke access from a web console; the lock talks to the cloud through a mains-powered bridge in the hallway (Wi-Fi to cloud, BLE to locks). The hardware is designed; this document covers firmware, bridge software, mobile apps and cloud.

## 1. Device and firmware

- FW-1. The lock runs on 4×AA batteries and must last at least 12 months at 20 operations per day; battery level is reported to the cloud daily and when it drops below 20 %.
- FW-2. The lock keeps working with no bridge and no phone connectivity: PIN codes and previously issued phone credentials are validated locally; the last 500 access events are stored on the lock and uploaded when a connection returns.
- FW-3. Firmware images are signed with Ed25519; the bootloader rejects an unsigned or downgraded image. Updates are delivered over the air via the bridge, applied only when the battery is above 40 %, and roll back automatically if the new image fails to boot twice.
- FW-4. A PIN attempt after 5 wrong PINs in 10 minutes is refused for 5 minutes; the event is reported.
- FW-5. The lock exposes a BLE GATT service; every command is encrypted with a per-lock key provisioned at the factory, and phone credentials are time-bounded tokens signed by the cloud and verified by the lock offline.
- FW-6. The keypad must remain usable with gloves in −20 °C; not a software requirement, listed for completeness.
- FW-7. Manual override with a physical key is always possible; the firmware must never be able to prevent mechanical opening.

## 2. Bridge

- BR-1. The bridge connects up to 60 locks over BLE and to the cloud over Wi-Fi (WPA2/WPA3) or Ethernet, using MQTT over TLS 1.3 with a per-bridge X.509 certificate issued at manufacture.
- BR-2. The bridge buffers up to 72 hours of lock events when the cloud is unreachable and forwards them in order when it reconnects.
- BR-3. A command from the cloud (unlock, revoke credential, update schedule) reaches the lock within 3 seconds in 99 % of cases when the bridge is online.
- BR-4. The bridge software is updated over the air independently of lock firmware; updates are staged to 1 % of bridges for 24 hours before general rollout.

## 3. Mobile app (iOS and Android)

- APP-1. A resident opens their door by holding the phone near the lock; the app works without internet access once a credential is cached.
- APP-2. A resident can share a time-limited guest credential (1 hour to 7 days) with another person by link; the guest needs the app but not an account.
- APP-2b. A resident can revoke a guest credential they shared; revocation follows CL-2.
- APP-3. The app shows the resident's own access history for the last 90 days.

## 4. Cloud and property-manager console

- CL-1. A property manager creates buildings, doors and residents, and assigns credentials (phone, PIN, or both) with optional schedules (e.g. cleaner 08:00–12:00 weekdays).
- CL-2. Revoking a credential takes effect on the lock within 10 seconds when the bridge is online, and at the next bridge contact otherwise; the console shows whether the revocation has been confirmed by the lock.
- CL-3. Every unlock, lock, failed attempt and administrative change is stored for 2 years and exportable as CSV per building.
- CL-4. The console shows per building: offline locks, locks with battery below 20 %, and firmware version distribution; an alert email goes to the manager when a lock has been offline for more than 24 hours.
- CL-5. Fleet firmware rollout: the manager (or Halden support) selects a firmware version and a percentage of locks per building; rollout pauses automatically if more than 2 % of updated locks fail to report back within 1 hour.
- CL-6. Public REST API for property-management systems (PMS) to create residents and credentials; OAuth2 client credentials; 300 requests per minute per PMS integration.
- CL-7. Emergency unlock of all doors in a building by the fire service through a dedicated role and a second-factor confirmation; the action is logged and the building manager is notified.
- CL-7b. A property manager can export a monthly PDF report of access events per building; the report is generated within 5 minutes of the request.
- CL-8. Data residency: EU customers' data stays in the EU; US customers' data in the US. A building belongs to exactly one region.

## 5. Scale and constraints

- Year-1 fleet: 40,000 locks, 1,200 bridges, 55,000 residents. Year-3 target: 400,000 locks.
- Typical load: 20 operations per lock per day; event bursts at 07:00–09:00 (about 5× the average).
- Firmware: C on Zephyr RTOS (nRF52840). Bridge: Go on Linux (Yocto). Cloud: Go services, PostgreSQL, existing MQTT broker (EMQX) and Kubernetes on GCP. Mobile: Kotlin and Swift.
- Team: 3 firmware, 2 bridge, 5 cloud, 3 mobile, 1 QA, 1 security.
- Certification: the BLE stack must be Bluetooth SIG qualified; the radio is already certified (CE/FCC).

## 6. Out of scope

- Video doorbell and camera features (separate product).
- Integration with third-party locks.
- Replacing the hardware's secure element or the factory provisioning tool.

## 7. Open questions

- Do we need PIN codes to work on the lock before it has ever been online? (Provisioning flow.)
- Is a 12-month battery life enough for the Nordic market, or should FW-1 be 18 months?

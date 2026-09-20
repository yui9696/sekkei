# Contract signing portal

## Requirements
- A customer can sign a contract with a qualified electronic signature (eIDAS) provided by the existing DocuSeal integration; the signed PDF is stored for 10 years.
- Both parties are notified by email when the contract is fully signed.
- Firmware for the card readers is signed with the vendor's Ed25519 key; the portal verifies the signature before offering a firmware file for download.

## Constraints
- TypeScript, PostgreSQL. Team: 3 engineers.

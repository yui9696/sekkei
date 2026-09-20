# Housing Benefit Online Application — Service Specification (Alpha → Beta)

Department for Communities, Digital Service · Service owner: Rhiannon Pugh · Version 0.9 (Beta candidate) · 2026-09-17

## 1. Service description

Residents of the four participating councils apply for Housing Benefit and Council Tax Reduction online instead of on the 28-page paper form. Caseworkers assess the application in the existing case management system (Northgate Revenues & Benefits, on-premises at each council). The service must meet the GOV.UK Service Standard and be assessed before public Beta.

## 2. Users

- Applicants: about 180,000 households per year across the four councils; 41 % use only a mobile phone; 12 % have a declared disability; 9 % need Welsh; an estimated 6 % have no email address.
- Caseworkers: 260 across the councils.
- Assisted digital: 3 support-centre teams (phone and in-person) who complete the form on the applicant's behalf.

## 3. Accessibility and inclusion — mandatory

- ACC-1. The service must conform to WCAG 2.2 level AA; conformance is verified by an external audit before public Beta and re-audited after every release that changes a page.
- ACC-2. Every page must be usable with keyboard only, with a screen reader (NVDA + Firefox, JAWS + Chrome, VoiceOver + Safari on iOS), and at 400 % zoom without horizontal scrolling.
- ACC-3. The service must be available in English and Welsh; the applicant can switch language on any page without losing entered data. Welsh must not be a machine translation.
- ACC-4. An applicant can save and return to an application for up to 30 days using a reference number and their date of birth; no account or email address is required.
- ACC-5. Timeouts: after 20 minutes of inactivity the applicant is warned and can extend the session; unsaved answers are not lost on timeout, they are kept for the return journey.
- ACC-6. Error messages must identify the field, say what is wrong and how to fix it, in plain language at a reading age of 9; the error summary must receive focus.
- ACC-7. Applicants must not be asked for information the council already holds; the postcode lookup pre-fills the address and the council is derived from it.
- ACC-8. Documents (payslips, tenancy agreement, bank statements) can be uploaded as photos from a phone; each file up to 10 MB, JPEG/PNG/PDF/HEIC; the applicant sees a thumbnail and can remove a file before submitting.
- ACC-9. Assisted-digital staff complete the form in the same service acting for the applicant; the application records that it was assisted and by whom.
- ACC-10. The service must work without JavaScript; JavaScript enhances but is not required for any step.

## 4. Functional

- F-1. The application has 9 sections (about you, partner, address, income, savings, rent, other people in the household, bank account, declaration); the applicant can complete them in any order and sees which are complete.
- F-2. Eligibility is not decided online; the service gives an indicative outcome ("you may be entitled to …") based on the answers, clearly marked as not a decision.
- F-3. On submission the applicant receives a reference number on screen and, if they gave an email or mobile number, by email or SMS through GOV.UK Notify; the confirmation is not sent to applicants who did not give contact details.
- F-4. Submitted applications are delivered to the applicant's council's Northgate system within 15 minutes as an XML case file over the council's SFTP; documents are attached as PDF (images converted to PDF); a delivery failure is retried for 24 hours and then raised to the service desk.
- F-5. Caseworkers can request additional evidence; the request is sent by the applicant's preferred channel (email, SMS or letter — letters are printed and posted by the existing print contractor via a nightly PDF batch) and the applicant uploads the evidence against the same reference number.
- F-6. The applicant can withdraw an application before it has been decided; a withdrawal is transmitted to Northgate like a submission.
- F-7. A caseworker tool `benefits-admin` (command-line, used by the two service administrators) re-sends failed deliveries, lists applications by council and status, and purges applications past retention; every run is logged with the operator's name.
- F-8. Declarations are signed by the applicant ticking a statement; no drawn or electronic signature is required. The submitted application, including the declaration text and timestamp, is rendered to a PDF the applicant can download.

## 5. Data and retention

- D-1. Applications not submitted within 30 days are deleted; submitted applications and their documents are deleted from the service 90 days after delivery to the council (the council's system is the record).
- D-2. Bank account numbers are stored encrypted and are never included in emails, SMS or logs.
- D-3. No analytics cookies without consent; the cookie banner must not block the page and must be accessible.
- D-4. All data stays in the UK.

## 6. Non-functional

- N-1. Availability 99.5 % (07:00–23:00 daily); maintenance outside those hours.
- N-2. Peak: about 1,200 applications per day in the first week of April (rent increases), otherwise 500 per day; a page must render in under 1 second at the 95th percentile on a 3G connection for the HTML, with images and fonts loaded progressively.
- N-3. The service must not depend on any third-party JavaScript or fonts loaded from outside the service's domain (privacy and resilience).
- N-4. Security: OWASP ASVS level 2; all uploads are virus-scanned before a caseworker can open them; a file that fails the scan is quarantined and the applicant is asked to re-upload.

## 7. Constraints

- GOV.UK Design System components and the GOV.UK Frontend must be used; the prototype is in the GOV.UK Prototype Kit.
- Hosted on the department's existing platform (AWS London, Kubernetes); Ruby on Rails is the department's standard; PostgreSQL.
- Team: 2 developers, 1 designer, 1 content designer (Welsh), 1 user researcher, 1 delivery manager; an accessibility specialist is available 2 days a week.
- Beta assessment booked for 2027-01-20.

## 8. Not in scope

- Changes to how councils assess claims or to Northgate itself.
- Universal Credit (DWP) applications — the service signposts to GOV.UK.
- Payments to applicants (made by the councils).

# Second evaluation: three unseen specifications, two of them in Japanese (2026-09-17)

Same protocol as [EVALUATION_2026-09-11.md](EVALUATION_2026-09-11.md): the specifications
were written *after* the day's engine changes (Japanese input, the catalogue extension,
`deliver`, `redteam`) and run through `sekkei design` unchanged. "Before" is the first run;
"after" is after the fixes that run motivated (same day, listed below). Scores are the
author's judgement on ten architect's criteria, 0/1/2 each, with the evidence so they can
be disputed. The rewrite tables in each `NOTES.md` §7 are part of the evidence for the
Japanese specs.

| spec | language | domain | why it is hard |
|---|---|---|---|
| `examples/eval2/gairai.md` | Japanese | hospital outpatient booking: slots, reminders by email/SMS, EHR integration, APPI | multi-clause sentences (「診療科と医師を選び、…登録・変更・キャンセルできる」), double-booking, a legacy system named in Japanese |
| `examples/eval2/gakushu.md` | Japanese | corporate LMS: video courses, quizzes, manager dashboards, two locales | 2 GB uploads and 2,000 concurrent viewers (media delivery), prohibitions (「失われてはならず」), localisation |
| `examples/eval2/loans.md` | English | loan origination: KYC + credit bureau, scoring model, underwriter workflow, core-banking export, 7-year retention | an external verification step the catalogue did not know, an approval workflow with escalation, PII + regulators |

## Scores

| criterion | gairai (ja) | gakushu (ja) | loans (en) |
|---|---|---|---|
| 1. Requirements fidelity | 1 → 1 | 1 → 1 | 2 → 2 |
| 2. Numbers preserved as metrics / preconditions | 1 → 2 | 2 → 2 | 2 → 2 |
| 3. Component decomposition | 1 → 2 | 0 → 2 | 1 → 2 |
| 4. Interfaces and operations | 1 → 1 | 1 → 1 | 0 → 1 |
| 5. Decisions correct for the constraints | 2 → 2 | 1 → 2 | 1 → 2 |
| 6. Data model | 1 → 1 | 1 → 1 | 1 → 1 |
| 7. Work packages | 1 → 1 | 1 → 1 | 1 → 1 |
| 8. Architect's notes (questions, capacity) | 1 → 1 | 1 → 1 | 1 → 1 |
| 9. Threats and risks relevant | 2 → 2 | 2 → 2 | 2 → 2 |
| 10. Honesty (nothing invented silently) | 2 → 2 | 2 → 2 | 2 → 2 |
| **total / 20** | **13 → 15** | **12 → 15** | **13 → 16** |

For comparison, the 9/11 evaluation ended at 15/15/16 on English specs. Japanese input
lands two points lower on fidelity and interfaces — the cost of a glossary instead of a
parser — and the same everywhere else.

## Evidence, per spec

### Outpatient booking, Japanese (13 → 15)

Before: 「1 日あたり 3,000 件」 came out as `1 3000 requests/day` (a stray token in the metric);
the EHR integration sentence (「既存の電子カルテシステム(基幹システム)へ…夜間に連携する」) was
not recognised because the legacy pattern looked for `existing system` with nothing in
between; 「診療科と医師を選び、空き枠から診察予約を登録・変更・キャンセルできる」 was
rewritten as one clause with the objects tangled (`cancel doctors and availability slots
from appointments`).

After: the per-day rate grammar (`3000 requests/day`, 20 requests/s peak as the second
quantity); the legacy pattern accepts up to three words before `system`, so an *Existing
system* + *Legacy system adapter* appear (the batch-file exchange wins the integration decision because the text says 「夜間に」, which the engine reads as a nightly-batch constraint — at the first run the API façade had won by 0.04); multi-clause
sentences are split at 「〜び、」「〜し、」 and the first clause's actor carries over
(`Patients departments choose doctors. The system can register, change and cancel
available slots from appointments.` — still rough, but each clause now has its own verb).
Right from the start: PostgreSQL, OIDC, optimistic concurrency for the double-booking
rule, platform encryption at rest with access audit for the patient data (field-level encryption scored lower on simplicity for a team of 3), SMS + email notifier, audit log, slot generation as a
scheduled job, data-protection component for APPI deletion.

Still wrong: `POST /slots` where a human would write `POST /appointments`; `GET
/informations/{id}` (基本情報 → "basic information" became an object); the two
unrecognised sentences are exactly the two multi-clause ones, placed by the fallback.
**A human still adds**: the appointment state machine (booked → changed → cancelled with
the slot released), and the naming.

### Corporate LMS, Japanese (12 → 15)

Before: 「公開」 → `publish` activated *event ingestion* (an Ingest API and a Work queue for
a course catalogue); 「画面」 → `screen` activated the *local user interface* pattern; no
component for 2 GB videos watched by 2,000 people; 「日本語と英語」 did not activate
localisation because the glossary rendered it as `Japanese and English` inside a sentence
the i18n signals did not cover; 「成績は失われてはならず」 lost its prohibition (`Grades
lost.`).

After: event ingestion needs `publish ... events` (or two other signals), so a published
course is just a CRUD operation; 「画面」 → `pages`; a *media* pattern (video, playback,
CDN) with the decision *object storage behind a CDN with signed URLs, the application
never streams bytes* and a CDN external; 「ロケール」/「日本語・英語で表示」 reach the
localisation pattern (ICU message catalogues); prohibitions on quality sentences are
rendered as `Grades must never be lost` and the durability tactic accepts `never be
lost`.

Still wrong: quiz attempts and enrolments are not entities (Course, Grade, Test, Video
are); `GET /managers` is noise from 「上長は…閲覧できる」; the capacity table rests on the
engine's assumed 20 requests/s because the text states viewers, not a request rate (the
notes say so). **A human still adds**: the enrolment/attempt model and the video upload
flow (multipart to object storage, then the 10-minute completion rule).

### Loan origination, English (13 → 16)

Before: *applicant* and *underwriter* were not in the actor lexicon, so the Public HTTP API
had **no operations at all** and two components were synthesised from the fallback
("Applicant processor", "Copy processor"); no KYC component (the catalogue had no such
pattern); a *Vector index for semantic search* decision appeared because the model-inference
pattern dragged it in; "request deletion" and "copy of their data" did not reach the
personal-data pattern; the words "for regulators" and "who took it" did not reach the
audit-log pattern.

After: 60 new actor nouns; a *kyc* pattern with an *Identity and credit checks* component
(timeouts, raw responses recorded), the external provider, the verification flow and the
provider-outage risk; the vector decision is only triggered by embeddings/semantic search
(a new *semantic_search* pattern) or a stated vector database; the personal-data and
audit-log patterns accept the regulatory phrasings. The API now has `POST /applications`
(a parenthesis ends the noun run, so `(amount, term, …)` no longer makes it `POST
/amounts`), `POST /documents`, `GET /status/{id}`, approve/reject, `GET /copies/{id}`,
`POST /deletions/{id}/request`. Decisions: explicit state machine for the workflow,
batch file exchange with the core banking system, platform encryption + access audit for
PII, two instances per role for 99.9 %.

Still wrong: `POST /reasons/{id}/approve` (the object should be the application; "with a
reason" won); no *Application* entity (Document, Decision, Account, Credit, Input are
there — the entity extractor reads nouns, not roles); the underwriter queue is a work
package on the workflow engine, not an explicit queue interface. **A human still adds**: the
application state machine with the 2-business-day escalation as a timer, the queue view
for underwriters, and the model-version pinning contract.

## What the red team said about the same designs

`sekkei redteam` on the three specs, after the fixes: no high findings; 3 / 1 / 0
unrecognised sentences (RT07) — exactly the sentences listed above as still wrong; the
assumption load (RT06) on the hospital spec (9 decisions proposed against 8 taken from the
text) — the notes list the nine questions. The reports are in
`examples/eval2/*.REDTEAM.md`.

## After the independent red team (same day)

An independent reviewer (a separate session, given no conclusions) attacked the same four
specs and found what the scores above had not: the language decision was lost when the
engine re-read the augmented text (a Japanese spec with few bullets came back raw and
「300ms 以内」 became a 300 s metric — fixed: the language is decided once on the original);
the load question derived a rate from a catalogue *count* (200,000 items → 2,000 requests/s
→ 10 TB/month — fixed: a count is a size, never a rate; the default is labelled a default);
the retention default deleted domain records after 90 days (fixed: domain data indefinite,
logs and history one year); runbooks and FMEA looked for the backup decision by title
prefix and never found the engine's assumed one (fixed); two critical-path weight tables
(fixed: one table, person-days); acceptance templates were chosen by component family, so a
PII requirement was checked by the SSRF test (fixed: chosen by the metric's quality);
SLO.md paged on assumptions and record sizes (fixed: stated latency/availability/rate/loss
only); the FMEA propagated an email-provider outage into every must-have (fixed: side-effect
components do not propagate); `redteam` was quadratic (capped); `--prices` accepted NaN,
negatives and nested objects (rejected). The reviewer's own spec (smart-building access
control) scored **5/20**: the decision hot path, device PKI, offline controller cache and
regional topology were all missed — the catalogue has none of them. That number stands as
the honest floor for a domain the catalogue does not know.

## The fixes this evaluation motivated

- Japanese: per-day/per-hour rate grammar (「1 日あたり N 件」), prohibition rendering for
  quality sentences (「〜てはならず」), clause splitting with actor carry-over, ~40 domain
  words (診療科, 空き枠, 電子カルテ, 受講, 視聴位置, 再生, ロケール, …), 「画面」 → pages.
- Catalogue: *kyc*, *media*, *semantic_search* patterns; event ingestion requires
  `publish … events`; the vector-store decision no longer follows every model; the legacy
  pattern accepts `existing <words> system`; personal-data and audit-log patterns accept
  regulatory phrasings; 60 actor nouns; a parenthesis ends a noun run in operation naming.
- The three earlier evaluation specs were re-run: ride and telemetry unchanged except one
  operation name on the engine-assumed retention bullet; document search gains a Reporting
  component for its weekly report.

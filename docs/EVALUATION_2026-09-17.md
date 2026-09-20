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

## Second independent red team (2026-09-19): specifications as teams write them

A second reviewer, again given no conclusions, wrote six specifications the way engineering
teams actually hand them over — a Confluence design doc with a `| Field | Value |` header
table and a requirements table, a Jira epic export whose stories are prose lines
(`VOD-2211 As a viewer, I want …`) with Given/When/Then beneath, meeting notes with speaker
labels and TODOs, a Japanese 要件定義書 with a glossary table, a one-paragraph Slack message,
and a change request against five named existing services — plus eight robustness inputs
(PDF paste, BOM+CRLF, smart quotes, tabs, a 300-line spec, mixed Japanese/English, a
table-only spec, a two-line table header). Its scores on the engine as it stood that
morning were **5 / 3 / 4 / 9 / 8 / 4 out of 20**, median 5, and its verdict was that the
team would not adopt the generator, only the checking side. The findings (five blockers):

- every prose user story was silently dropped, because a document with bullets discarded
  prose without a modal word; the pattern matcher still read the dropped text, so the design
  had a geospatial index for a requirement it did not have;
- `500 clip requests per second`, `400 orders per second`, `200 verifications/minute` were
  discarded as HTTP status codes;
- `<20ms` became 20 seconds (the `m` read as a multiplier) and `over EDI … within 15 minutes`
  took the earlier comparator (`> 15 minutes`);
- 「改ざん不可」 (tamper-proof) was rewritten as "allowed";
- a change request was designed as a greenfield system and its "5. Rollout" section landed
  in the preceding "Out of scope" section as non-goals.

All of these, and the majors (metadata tables becoming components and tickets, team sizes
read from names instead of counts, an in-memory queue for a bank OMS, "no public cloud"
read as public users, SQLite from "offline training reads", the kill switch read as a
feature flag, SLOs on retention periods with doubled units and a full-month window for a
trading-hours target, a hyphen-wrapped PDF line becoming the requirement "00.", stale ADRs
surviving a re-run, open questions dropped and reported as zero) are now regression tests
in `tests/test_real2.py` over the reviewer's own files in `examples/real2/`. What the engine
does differently since: prose is a requirement when it has an actor as subject and a verb or
a bounded number; every sentence it read and did not take is listed in the notes; the
"stated in the constraints" bonus and the exclusions count only tokens the author wrote,
never the engine's own assumed answers; volatile options (in-memory queue, in-process
timers) are unavailable whenever durability is required; Japanese rewrites that lose a
negation are flagged. Not re-scored by the reviewer; the honest statement is that the
listed failures no longer reproduce, not that the scores are now higher.

## Third independent red team (2026-09-20): a consultancy deciding whether to use it with clients

The third reviewer wrote a government tender annex (`B.2.4 The Platform shall …`, "is excluded
from this Contract", "for information only, not a requirement"), a PRD with a KPI table and user
segments ("Claims handlers (team of 45)"), a Japanese 提案依頼書 with 第N章 headings and 全角
numbers, a platform RFC with stated routes, an incident post-mortem whose action items are the
requirements, and a Notion page with emoji headings, callouts, `<details>` blocks and a "🚫 Not in
scope" line — plus eight accidental-input tests. Scores on the engine as it stood: **1 / 4 / 2 /
4 / 5 / 2 out of 20**; on re-scoring the previous six specs with fresh eyes: 10 / 7 / 2 / 9 / 2 /
5. Verdict: not client-facing; usable internally as a coverage checklist and a boilerplate
generator for the generic layer.

The blockers, all reproduced and all now regression tests in `tests/test_real3.py`:

- **Prohibitions inverted into operations.** "shall not discard any measurement" produced
  `discard_measurement`; "Operators shall not be able to delete alarms" produced `delete_alarms`;
  "Do not store bank account numbers" produced an *Account processor* with `store_account`. A
  verb under *not / never / cannot / shall not* is now a forbidden action: it never becomes an
  operation, the sentence becomes a non-functional rule the core enforces, and no component is
  synthesised from it.
- **One stray word re-architected the system.** "Remote **Terminal** Units" made the platform a
  CLI with SQLite; "screen-failure reasons" a local UI; "drawn **signature**" an HMAC signer with
  a secret store; "payments" in a payout system a `POST /charges`. The signals are narrower now
  and a payouts pattern exists.
- **In-memory primary store under a durability requirement** (the exclusion existed for the
  queue and the timers, not the store).
- **Fabricated load** — "IEC 60870 specialist" read as 60,870 people and turned into 2.7 TB/day.
  Populations must be countable nouns, never a standard's number; the rate now multiplies by the
  items per report (4,200 RTUs × 64 points ÷ 4 s).
- **Exclusions designed in** — "Metering for billing purposes is excluded" became a component
  and a ticket; the post-mortem's timeline and root causes were requirements; the Notion page's
  raw `<details>` HTML was a requirement. Exclusion clauses are filed under out of scope,
  reference-only sections are skipped, timelines/root causes/what-went-well are background,
  HTML and emoji are stripped, and action items in a post-mortem are the requirements.
- **Positional ids** — two added bullets renumbered every requirement, `diff` reported 15 of 16
  packages stale and every ticket body changed. `diff` now matches elements by content and
  reports renumbering separately; issue bodies carry a `sekkei-key` marker and the script
  upserts.

Also fixed from the majors: KPI-table cells that were not the widest column (the targets) were
lost; "team of 45" (a user segment) was the team; "could not decide" made a requirement
optional; an existing RabbitMQ lost to a PostgreSQL queue; a rejected alternative was rendered
as chosen; stated `GET /v2/queue/{ticket}` routes were renamed; Japanese 第N章 headings and the
agricultural glossary; passive verbs ("is booked", "defined in the protocol") were operations.
As before: not re-scored by the reviewer — the failures no longer reproduce.

## Fourth independent red team (2026-09-20): re-scoring, and the over-corrections

The fourth reviewer first re-scored the twelve specifications of reviewers 2 and 3 with fresh
eyes, before reading any earlier score:

| spec | reviewer 2 | reviewer 3 | reviewer 4 |
|---|---|---|---|
| real2/01 FX options OMS | 5 | 10 | 7 |
| real2/02 live-to-VOD epic | 3 | 7 | 4 |
| real2/03 ML platform notes | 4 | 2 | 6 |
| real2/04 在宅患者モニタリング (ja) | 9 | 9 | 8 |
| real2/05 flaky-test tracker (Slack) | 8 | 2 | 6 |
| real2/06 split payments CR | 4 | 5 | 7 |
| real3/01 grid telemetry tender | — | 1 | 5 |
| real3/02 pet-insurance PRD | — | 4 | 7 |
| real3/03 農業 IoT 提案依頼書 (ja) | — | 2 | 6 |
| real3/04 matchmaking RFC | — | 4 | 7 |
| real3/05 e-discovery post-mortem | — | 5 | 7 |
| real3/06 clinical-trial Notion page | — | 2 | 6 |

Median 6.5, nothing above 8. The reviewer's reading of the flat zeros: on every spec the data
model is `(id, created_at)`, the interfaces are verb–noun fragments, and the work packages are
catalogue components at S/M/L — those three criteria are not moved by parsing fixes.

Its own six specs (a security questionnaire answered in a `| # | Question | Answer | Status |`
table, an ERP change table, a hardware+firmware+cloud product, a WCAG-heavy public-sector
service, a bilingual ja/en live-ops spec, a diagram-heavy research platform with five deliberate
contradictions) scored **1 / 5 / 5 / 6 / 4 / 6 / 2**. Four blockers were over-corrections of the
round-3 fixes, all regression tests now: bullets starting with `#` (issue numbers, a `#` table
column) were read as headings and vanished; "X are excluded from the export; the export must…"
inside a requirement bullet deleted the bullet (`_BULLET.sub` on a regex that matches the whole
line returned an empty string); `## 8. Not in scope` was not a heading because of the period; and
the red team's deletion attack silently skipped every requirement it could not locate — table
rows, numbered clauses, wrapped bullets, Japanese rows with `2.1` ids — and reported a green
result over the rest. Also fixed: team counts summed only a fixed role list ("3 firmware, 2
bridge, 5 cloud, 3 mobile, 1 QA, 1 security" → 4); a burst ("400/s at the London open", "120,000
rps for 5 minutes") was extrapolated to a month; a per-lock rate was never multiplied by the
fleet; an unrelated count was divided by an interval; a 10× peak was invented for a fixed-interval
feed; a maintenance window was taken as the service window; `--submits-->` diagram arrows and one
admin CLI made a whole web service a CLI with SQLite and no authentication; "support-centre
teams" made a Microsoft Teams provider and "pays for" a payment provider; "may degrade" in a
caveat clause made an availability target optional; CURRENT / N/A / STD rows of a status table
were work; IEC 62443, 21 CFR Part 11 and −20 °C were quantities; a per-jurisdiction residency
requirement got a single region. `redteam` now reports contradiction candidates (retention vs
deletion, residency vs hosting, anonymity vs identifiers, a forbidden practice vs "happens
today") and lists what it could not test; `diff` re-maps requirement ids inside acceptance
descriptions so a two-bullet change stales the packages that got the bullets, not all of them.

Not re-scored by this reviewer after the fixes. The honest state after four rounds: the engine
reads what teams write far more faithfully than it did (round 3's median 5 → round 4's 6.5), it
says what it dropped, and it is safe to use as a coverage checklist and a generator of the
generic layer; the domain-specific decomposition, the data model, the interfaces and the effort
remain a person's work, and every capacity table must still be checked against the text.

## The three flat zeros (2026-09-20, after the fourth round)

Every reviewer scored the data model, the interfaces and the work packages 0/2 on every
specification, and the fourth said why: those criteria are not moved by parsing fixes. An
entity was a noun with `(id, created_at)`; an operation was a verb–noun fragment (`POST
/prices/{id}/amend`); a package was a catalogue component at S/M/L regardless of content.

`engine/domain.py` reads the domain model from the sentences instead: fields from a
parenthesised attribute list, a `with A, B and C` list after a create/submit verb, a
possessive or an "amend the X of a Y"; types from the field names; state machines from the
transactional verbs applied to the entity and from `a → b → c` lists; invariants (never twice,
immutable after creation, same transaction, concealed) with the sentence that states them;
relations from "belongs to", "per", "has N". Proper nouns, verbs, adjectives and words that never
occur as a determined or plural noun are not entities. Related entities form an aggregate, and
each aggregate is a component that owns its records and their transitions, with its own work
package; sentences about its entities are owned by it instead of a synthesised "X processor".
Operations name the entity, not its attribute (`POST /orders/{id}/amend`). Package sizes come
from what a package carries (operations, entities, requirements).

On the FX-options spec this reads `Order(instrument, notional: Money, strike: Money, expiry:
timestamp, direction: enum, limit_price: Money, status: working → submitted → cancelled →
rejected)`, `Fill(status: booked → retrying → rejected; immutable after creation)`, an Order
domain and a Fill domain with `submit_order / cancel_order / book_fill / retry_fill`, and no
"Precision processor" or "Officer controller". Not re-scored by an independent reviewer yet;
that is the next round's job.

## Fifth independent red team (2026-09-20): did the three criteria move?

Fresh-eyes re-score of all 18 specs after the domain model landed: average 6.6 (before 6.5); data
model 1/2 on 3 of 18, interfaces 1/2 on 4, work packages 0 on all. The reviewer's four attack
specs (fields spread over sentences, a state machine in prose, a homonym, tech-name-heavy prose)
scored 7 / 9 / 6 / 3 and found why the module had not moved the numbers: `verb_of` did not
undo a doubled consonant, so `shipped`, `cancelled`, `submitted` mapped to nothing and eight of
the state verbs were unreachable; fields were read from four surface forms only ("X has a, b and
c" gave nothing); states were rendered as a chain that was never read; invariants attached to
the first-inserted entity; "Team of 5, Go, Kafka and ClickHouse" became a team of two people
named Go and Kafka; packages were "satisfied" by every sentence containing the entity's word;
routes like `POST /anothers/{id}/assign` came from any verb + noun.

All fixed and turned into tests (`tests/test_domain.py`, `examples/real5/`): inflection;
"has/records/carries" lists and "set its A, B and C"; real transitions from "placed, then
confirmed, then shipped", "may cancel until it is shipped", "must confirm or decline within 2
hours, otherwise it expires" and `a → b/c → d` arrow lists (`status in (placed)` preconditions
on the transition operations); negated rules attached to the sentence's subject ("cancel is not
allowed once shipped", "immutable once shipped"); a person is never read from a tech name;
aggregates are satisfied only by the sentences that built them, and sized by functional scope;
a REST resource must be a thing the text keeps; one-off nouns and people no longer become "X
processor" components (a reader/controller is still synthesised for physical sources such as
sensors). On the reviewer's order spec the engine now reads `Order(delivery_address,
delivery_slot; placed → confirmed → shipped, placed → declined, → cancelled until shipped, →
expired; cancel not allowed once shipped; immutable once shipped)` and offers
`confirm_order / decline_order / ship_order / cancel_order / expire_order` with their allowed
source states. Not yet re-scored by an independent reviewer.

## Sixth independent red team (2026-09-21): the domain layer was overfitted

Fresh-eyes re-score of 22 specs after the domain layer and the fifth-round fixes: the 18
specs of rounds 2–4 average **6.3** (fifth reviewer 6.5) and the four specs of round 5,
against which the fixes were written, average **10.3** (fifth reviewer 6.3). C6 (data model)
is 1/2 on 4 of 18, C4 (interfaces) 1/2 on 4, C7 (work packages) 1/2 on 4 — the same four —
and 2 on none. The reviewer named the evidence in the code: field names from one spec
whitelisted in the reader, stop-lists holding words from three others, three sequence
regexes that were the three sentences of one spec. Its five attack specs (fields in other
prose forms and tables, a state machine as a table, homonyms and a many-to-many, arithmetic
business rules, Japanese fields/states) scored **5 / 8 / 9 / 5 / 4**: zero of fourteen stated
fields read in form (a), transition tables not read in (b) while the output asserted "not
stated in the text", both senses of "account" impossible by stop-list in (c), 2 of 8 rules in
(d), and a Japanese must-not inverted into a "ship is not allowed" invariant in (e).

What changed after it. The corpus constants are gone (a field word that is also a verb is
judged by an attribute-noun list, not a whitelist; "london/hallway/acquirer/region" no longer
block anything). The false statement is gone: a transition operation now says "allowed source
states not read by the engine (it reads 'then/until/otherwise' prose and a → b lists)". The
bugs that were bugs are fixed and tested: a 任意 (optional) row was deleted as "not work"; a
Japanese 「発送済みの注文はキャンセルしてはならない」 became "must not ship and cancel" (済み /
前 / 後 are now state adjectives and 「受付→発送→完了」 an arrow list); "an invoice cannot …"
produced a "Cannot processor" (non-nouns never seed a component, and a rule about an entity
the design owns goes to its aggregate); an arrow list `approved/held/rejected → paid` joined
rejected to paid (terminal states do not continue); a verbatim `DELETE /v2/queue/{ticket}`
was dropped when the sentence had no human actor; duplicate routes were renamed `/events-2`
instead of merged and noted; NBSP-grouped numbers ("2 000 ms") read as 0; HTML comments and
image links were read as sentences.

What did **not** change, on purpose: no new phrasings were added for the reviewer's five
attack specs. Writing readers for "is identified by", "we store for each X", a from/to
table, 「…を持つ」 would raise those five scores and prove nothing — that is exactly the
overfitting the review exposed. The protocol from round seven: the reviewer writes its
specifications, scores them, reports scores and defect *classes*, and deletes the
specifications; the engine's authors never see them. A phrasing gets a reader only when it
is reported as a class across several independent rounds.

Verdict adopted in the README: a requirements linter with a catalogue behind it. The
requirement table, numbers, team size, non-goals, open questions, the generic layer and the
dropped/assumed lists are reliable; the domain decomposition, data model, routes and work
packages are drafts a person rewrites.


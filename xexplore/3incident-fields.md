# Incident Fields Reference

_Based on Incident 1 — "Unlawful occupation and criminal damage — Lewes Castle, 17–19 March 2026" — in the local dev instance._

> **Key concept:** An incident is a **case folder** — it groups bulletins, actors, and events into a single documented violation. It has its own workflow (status, peer review) but no date fields of its own. The time span of an incident is inferred from the dates of its linked events.
>
> Compare with a **bulletin**, which is a raw source document. Bulletins are evidence; incidents are the analytical product built from that evidence.
>
> **There is no investigation or case layer above the incident.** The incident is the top-level unit. If multiple incidents are part of the same broader picture, the options are:
> - **itoi relationship** — link incidents as Related, Part of, or Led to. This is the intended approach.
> - **Shared labels** — apply a common label (e.g. "Lewes Heritage Trust Campaign") to group incidents loosely.
> - **Single incident** — fold related events into one incident rather than splitting. Less clean analytically.
>
> Some platforms have an "investigation" layer above incidents — Bayanat does not.

---

## Toolbar area

### ID
- **What it is:** Auto-generated internal identifier. Read-only.
- **Table/column:** `incident.id`
- **Incident 1:** `1`

### Assigned To
- **What it is:** The analyst currently responsible for this incident.
- **Table/column:** `incident.assigned_to_id` → FK to `user.id`
- **Incident 1:** Analyst Two

### Status
- **What it is:** Current workflow state. Drives the peer review process.
- **Table/column:** `incident.status` (`varchar`) — values come from `workflow_statuses` table
- **Incident 1:** `Assigned`

### Access Roles (lock icon)
- **What it is:** Groups that can see this incident. Same behaviour as bulletin access roles.
- **Only available when creating a new incident** — the field is hidden on the edit form.
- **Table/column:** M2M — `incident_roles` join table → `role.id`
- **Incident 1:** _(none — open access)_

---

## Main content fields

### Title
- **What it is:** The analyst's name for the incident. Bilingual (English + Arabic).
- **Table/column:** `incident.title` / `incident.title_ar` (`varchar(255)`, not nullable)
- **Incident 1:** `Unlawful occupation and criminal damage — Lewes Castle, 17–19 March 2026`

### Description
- **What it is:** Full analyst notes about the incident — what happened, context, summary. Stored as HTML (TinyMCE editor).
- **Table/column:** `incident.description` (`text`)
- **Incident 1:** _Summary of the three-day occupation, gate breach, negotiations, and arrests._

### Locations
- **What it is:** Links to the structured location hierarchy — where the incident occurred.
- **Table/column:** M2M — `incident_locations` join table → `location.id`
- **Incident 1:** `Lewes Castle, Lewes, East Sussex`

### Labels
- **What it is:** Unverified descriptive labels applied during triage.
- **Table/column:** M2M — `incident_labels` join table → `label.id` (`label.verified = false`)
- **Incident 1:** `Protest / Demonstration`, `Property Damage Alleged`, `Heritage Site Threatened`, `Trespass Alleged`

### Potential Violations
- **What it is:** Alleged violations that have not yet been confirmed. Applied during initial documentation.
- **Table/column:** M2M — `incident_potential_violations` join table → `potential_violation.id`
- **Incident 1:** `Public Order Offence`, `Criminal Damage`, `Trespass`

### Claimed Violations
- **What it is:** Violations that have been confirmed or formally charged. Applied after verification.
- **Table/column:** M2M — `incident_claimed_violations` join table → `claimed_violation.id`
- **Incident 1:** `Violent disorder (Public Order Act 1986, s.2)`, `Criminal damage (Criminal Damage Act 1971, s.1)`, `Aggravated trespass (Criminal Justice and Public Order Act 1994, s.68)`

### Events
- **What it is:** Timestamped occurrences documented within this incident. Each event has a title, type, from/to dates, and a location.
- **No date fields on the incident itself** — the incident's effective time span is derived from the earliest and latest event dates.
- **Table/column:** `event` table, linked via `incident_events` M2M join table.
- **Incident 1:**
  1. "Crowd forces entry through barbican gate" — **Incident** — 17 Mar 14:00–14:30
  2. "Police begin formal negotiations" — **Post-Incident** — 18 Mar 09:00–18:00
  3. "Castle cleared, seven arrests made" — **Post-Incident** — 19 Mar 07:00–11:00

### Related Bulletins
- **What it is:** Links to bulletins with a typed relationship and probability score.
- **Table/column:** `itob` table — `incident_id`, `bulletin_id`, `related_as` (int → `itob_info`), `probability`
- **Relationship types (`itob_info`):** 2 = Primary Evidence, 3 = Supporting Evidence, 4 = Context
- **Incident 1:**
  - Bulletin 1 (Lewes Clarion) — Context, Certain
  - Bulletin 2 (X post) — Primary Evidence, Certain
  - Bulletins 3, 4 (Facebook, Instagram) — Supporting Evidence, Likely
  - Bulletin 5 (TikTok) — Primary Evidence, Certain
  - Bulletin 6 (Eyewitness, Okafor) — Primary Evidence, Certain
  - Bulletin 7 (Albion Broadcasting) — Supporting Evidence, Likely
  - Bulletin 8 (Lewes & Weald Constabulary, day 2) — Supporting Evidence, Likely
  - Bulletin 9 (The National Courier) — Primary Evidence, Certain
  - Bulletin 10 (Lewes & Weald Constabulary, day 3) — Supporting Evidence, Likely

### Related Actors
- **What it is:** Links to actors with a typed relationship and probability score.
- **Table/column:** `itoa` table — `incident_id`, `actor_id`, `related_as` (int → `itoa_info`), `probability`
- **Incident 1:**
  - Thomas Ashdown — Participant, Certain
  - Rachel Pemberton — Participant, Certain

### Related Incidents
- **What it is:** Links to other incidents with a typed relationship.
- **Table/column:** `itoi` table — `incident_id`, `related_incident_id`, `related_as` (int → `itoi_info`), `probability`
- **Incident 1:**
  - Incident 2 (Phoenix Causeway) — Related, Likely _(same group, same day)_
  - Incident 3 (Meridian House criminal damage) — Led to, Likely _(campaign escalation, three days later)_

---

## Review / workflow fields

### Comments
- **What it is:** Internal analyst working notes. Not shown in the view card by default.
- **Table/column:** `incident.comments` (`text`)

### Review
- **What it is:** Peer reviewer's written assessment. Only shown when status = `Peer Reviewed`.
- **Table/column:** `incident.review` (`text`)

### Review Action
- **What it is:** The outcome chip shown alongside the review text.
- **Table/column:** `incident.review_action` (`varchar`)

### Peer Reviewers
- **What it is:** First and second peer reviewers assigned to this incident.
- **Table/column:** `incident.first_peer_reviewer_id`, `incident.second_peer_reviewer_id` → FK to `user.id`
- **Incident 1:** First: Analyst Three, Second: Analyst One

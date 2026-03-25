# Entity Overview — Lewes Castle Investigation
### Ouse Valley Rights Monitor · Bayanat demo instance

_Complete reference for all entities in the sample data. All names, organisations, and events are fictional._

---

## Incidents

| ID | Title | Assigned to | Status |
|---|---|---|---|
| 1 | Unlawful occupation and criminal damage — Lewes Castle, 17–19 March 2026 | Analyst Two | Assigned |
| 2 | Unlawful assembly and obstruction — Phoenix Causeway, Lewes, 18 March 2026 | Analyst One | Assigned |
| 3 | Criminal damage to construction equipment — Meridian House site, Lewes, 22 March 2026 | Analyst One | Assigned |

**Incident relationships (itoi):**
- Incident 1 → **Related** → Incident 2 · Likely _(same group, same day)_
- Incident 1 → **Led to** → Incident 3 · Likely _(campaign escalation three days later)_

---

## Bulletins

### Incident 1 — Lewes Castle occupation

| ID | Variable | Source | Date | Assigned | itob type | Probability |
|---|---|---|---|---|---|---|
| 1 | `b_pre` | Lewes Clarion | 3 Mar 09:15 | Analyst One | Context | Certain |
| 2 | `b` | X (Twitter) | 17 Mar 14:22 | Analyst One | Primary Evidence | Certain |
| 3 | `b_fb` | Facebook | 17 Mar 14:35 | Analyst Two | Supporting Evidence | Likely |
| 4 | `b_ig` | Instagram | 17 Mar 14:41 | Analyst Three | Supporting Evidence | Likely |
| 5 | `b_tt` | TikTok | 17 Mar 15:04 | Analyst One | Primary Evidence | Certain |
| 6 | `b_ew` | Witness Statement (Okafor) | 18 Mar 10:30 | Analyst Two | Primary Evidence | Certain |
| 7 | `b_bbc` | Albion Broadcasting | 18 Mar 17:45 | Analyst Three | Supporting Evidence | Likely |
| 8 | `b_sp` | Lewes & Weald Constabulary | 18 Mar 12:00 | Analyst One | Supporting Evidence | Likely |
| 9 | `b_grdn` | The National Courier | 19 Mar 14:20 | Analyst Two | Primary Evidence | Certain |
| 10 | `b_sp2` | Lewes & Weald Constabulary | 19 Mar 13:30 | Analyst Three | Supporting Evidence | Likely |

### Incident 2 — Phoenix Causeway

| ID | Variable | Source | Date | Assigned | itob type | Probability |
|---|---|---|---|---|---|---|
| 11 | `b_tesco_x` | X (Twitter) | 18 Mar 13:04 | Analyst Two | Primary Evidence | Certain |
| 12 | `b_tesco_bbc` | Albion Broadcasting | 18 Mar 19:10 | Analyst Three | Supporting Evidence | Likely |

### Incident 3 — Meridian House criminal damage

| ID | Variable | Source | Date | Assigned | itob type | Probability |
|---|---|---|---|---|---|---|
| 13 | `b_lw1` | Lewes & Weald Constabulary | 22 Mar 09:15 | Analyst Three | Primary Evidence | Certain |
| 14 | `b_lw2` | Lewes Clarion | 22 Mar 13:45 | Analyst One | Supporting Evidence | Likely |

### Bulletin events

| Bulletin | Event title | Type | Date/time | Location |
|---|---|---|---|---|
| 1 | Council approves demolition of Meridian House | Pre-Incident | 3 Mar 2026 | Meridian House, Harvey's Brewery Site, Lewes |
| 2 | Crowd forces entry through barbican gate | Incident | 17 Mar 14:00–14:30 | Lewes Castle |
| 2 | X post published by @lewes\_local | Publication | 17 Mar 14:22 | Lewes Castle |
| 3, 4 | Crowd forces entry through barbican gate | Incident | 17 Mar 14:00–14:30 | Lewes Castle |
| 5 | Crowd forces entry through barbican gate | Incident | 17 Mar 14:00–14:30 | Lewes Castle |
| 6 | Police begin formal negotiations | Post-Incident | 18 Mar 09:00–18:00 | Lewes Castle |
| 7 | Albion Broadcasting reports day 2 of occupation | Publication | 18 Mar 17:45 | Lewes |
| 8 | Witness statement taken by Lewes & Weald Constabulary | Post-Incident | 18 Mar 12:00 | Lewes Castle |
| 9 | The National Courier reports end of siege and seven arrests | Publication | 19 Mar 14:20 | Lewes |
| 10 | Lewes & Weald Constabulary confirms seven arrests | Post-Incident | 19 Mar 13:30 | Lewes Castle |
| 11 | Protest group occupies Tesco car park, Phoenix Causeway | Incident | 18 Mar 13:00–17:00 | Lewes |
| 12 | Albion Broadcasting reports secondary protest at Tesco Lewes | Publication | 18 Mar 19:10 | Lewes |
| 13 | Construction equipment vandalized at Meridian House site | Incident | 22 Mar 02:00–04:00 _(est.)_ | Meridian House, Harvey's Brewery Site, Lewes |
| 14 | Construction equipment vandalized at Meridian House site | Incident | 22 Mar 02:00–04:00 _(est.)_ | Meridian House, Harvey's Brewery Site, Lewes |

### Geo markers

| Bulletin | Title | Coordinates | Main? | Notes |
|---|---|---|---|---|
| 1 | Meridian House (proposed demolition site) | `50.87484, 0.01664` | No | Harvey's Brewery site |
| 2 | Lewes Castle | `50.8729, 0.0074` | **Yes** (black) | X post location |
| 3 | Approach road south of castle | `50.8718, 0.0068` | No | Facebook post location |
| 11 | Tesco Lewes — Phoenix Causeway | `50.8771, 0.0147` | **Yes** (black) | Tesco car park |
| 12 | Tesco Lewes — Phoenix Causeway | `50.8771, 0.0147` | No | |
| 13 | Meridian House demolition site | `50.87484, 0.01664` | **Yes** (black) | Scene of criminal damage |
| 14 | Meridian House demolition site | `50.87484, 0.01664` | No | |

> **Map colours:** Black = geo marker with `main=True` · Yellow = geo marker with `main=False` · Blue = structured location · Teal = event location

---

## Actors

| ID | Name | Position | Nationality | Assigned | Status |
|---|---|---|---|---|---|
| 1 | Thomas Ashdown | Organiser, Lewes Heritage Trust | UK | Analyst Two | Arrested, charged |
| 2 | Rachel Pemberton | Chair, Lewes Heritage Trust | UK | Analyst One | Arrested, released on bail |
| 3 | Kieran Moss | Volunteer, Lewes Heritage Trust | UK | Analyst Two | Not arrested |

### Actor details

**Thomas Ashdown** · `a`
- DOB: approx. 1984 · Occupation: Self-employed builder · Family: Married, 2 children
- Origin: Lewes · ID: `CRN/2026/LEW/00312`, Crown Court `T20261234`
- Events: Arrested (Lewes Castle, 19 Mar 07:30) · Charged (Lewes Police Station, 19 Mar 15:30)

**Rachel Pemberton** · `a2`
- DOB: approx. 1961 · Occupation: Retired secondary school teacher · Family: Widowed, 1 child
- Origin: Lewes · ID: `CRN/2026/LEW/00313`
- Events: Arrested (Lewes Castle, 19 Mar 07:30) · Released on bail (Lewes Police Station, 19 Mar 18:30)

**Kieran Moss** · `a3`
- Occupation: Postgraduate student, Southdown University · Family: Single
- Origin: Brighton · No ID numbers (not arrested)

### Actor–Incident links (itoa)

| Actor | Incident | Role | Probability |
|---|---|---|---|
| Ashdown | Incident 1 | Participant | Certain |
| Pemberton | Incident 1 | Participant | Certain |
| Moss | Incident 2 | Participant | Probable |

### Actor–Bulletin links (atob)

| Actor | Bulletin | Relationship | Probability | Notes |
|---|---|---|---|---|
| Ashdown | 2 (X post) | Appeared | Certain | Identifiable at front of crowd |
| Ashdown | 5 (TikTok) | Appeared | Probable | Man matching description, unconfirmed |
| Ashdown | 6 (Eyewitness) | Subject | Certain | Okafor confirms man matching description |
| Ashdown | 9 (National Courier) | Appeared | Certain | Named as organiser |
| Pemberton | 2 (X post) | Appeared | Probable | Likely in crowd, not individually confirmed |
| Pemberton | 9 (National Courier) | Appeared | Certain | Named as a leader of the occupation |
| Moss | 11 (Tesco X post) | Appeared | Certain | Identifiable at front of protest group |
| Moss | 12 (Albion Broadcasting) | Appeared | Probable | Likely present, not named |

### Actor–Actor links (atoa)

| Actors | Relationship | Probability | Notes |
|---|---|---|---|
| Ashdown ↔ Pemberton | Associate | Certain | Both named organisers of the occupation |
| Ashdown ↔ Moss | Associate | Probable | Connected via Lewes Heritage Trust |
| Pemberton ↔ Moss | Associate | Probable | Chair and volunteer of same group |

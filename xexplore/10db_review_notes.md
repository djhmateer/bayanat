# Bayanat — Schema & Codebase Review Notes

_Reviewed 18 March 2026. Scope: PostgreSQL schema, SQLAlchemy ORM models, and access control logic against a local development instance running the current `main` branch. Performance profiling and application business logic are out of scope._

---

## Summary

**76 tables — 106 foreign keys — 170 indexes**

The schema is appropriately complex for the domain, not over-engineered — but it has
some rough edges that will cause friction as the codebase grows.

---

## The complexity is justified by the domain

The three-entity core (`bulletin` = evidence, `actor` = person/org,
`incident` = violation folder) is a **well-established pattern** in human rights
documentation — it mirrors what OHCHR, Amnesty, and UN MPTF tools use. The M2M
network is large but each junction table carries real meaning: probability scores,
user attribution, relationship types. That is not padding — it reflects the actual work.

The PostGIS geometry, FTS tsvectors, and GIN indexes show genuine engineering care.
The design reflects deliberate choices throughout.

---

## Concerns

### 1. FK delete rules are uniformly `NO ACTION` (105 of 106)

Every deletion dependency is managed in Python, not the database. The database will
raise an error rather than clean up. In a production system with complex delete flows
this is a latent bug factory.

### 2. Virtually no `NOT NULL` constraints on core tables

| Table        | % constrained |
|--------------|---------------|
| `bulletin`   | 11%           |
| `actor`      | 7%            |
| `location`   | 6%            |

This is partly intentional (human rights data is often partial), but it means
**data quality is entirely enforced at the application layer**. Anything that
bypasses Flask — a migration script, a direct DB insert, a future API client —
can silently insert invalid data.

### 3. Inconsistency: `related_as` type differs between relationship tables

`atob.related_as` and `itoa.related_as` are `ARRAY(integer)` — a relationship
can carry multiple types simultaneously.
`itob.related_as` is a plain `integer`.

This inconsistency will catch out every developer who works on relationships, and
already caused a bug in early development. It should be resolved before the
codebase grows further.

### 4. `actor_profile` — 68 columns, 65 nullable

This table encodes a specific forensic/missing-persons workflow: dental records,
physical markings, seen-in-detention, known-dead status. If the deployment does not
need forensic documentation, these columns add unnecessary overhead in every query
plan and ORM load. The table is also hard to extend cleanly when most of its columns
are already optional free-text fields.

### 5. Denormalised columns that require manual maintenance

`location.full_location` and `location.id_tree` are computed strings that must be
regenerated in application code after any location change. The app provides
`regenerate_all_full_locations()` and `rebuild_id_trees()` for this, but both use
a separate database connection — meaning they cannot see uncommitted rows. A freshly
inserted location will have `NULL` in these columns until the session is committed and
the regeneration method is explicitly called.

---

## Access control — roles as access groups

Bulletins (and actors/incidents) carry a `roles` many-to-many relationship to the
`Role` table (`bulletin_roles` join table). These roles act as **access groups**:
an entity is visible only to users who share at least one of its assigned roles.

The `can_access` logic is as follows:

| Situation | Result |
|---|---|
| User has `Admin` role | Always has access |
| Entity has roles assigned AND user shares at least one | Access granted |
| Entity has **no** roles assigned AND `ACCESS_CONTROL_RESTRICTIVE` is off | Access granted (open) |
| Entity has roles assigned AND user shares none | Access denied |

Roles therefore serve double duty: they are both a user's group membership and an
entity's visibility tag. This is a compact and workable design, but the dual
semantics should be clearly documented for new contributors.

---

## Ease of change

| Type of change | Difficulty | Reason |
|---|---|---|
| Add a new field to bulletin / actor / incident | **Easy** | Schema is permissive; add a nullable column and ORM field |
| Add a new reference / lookup table | **Easy** | Well-established pattern; follow existing `*_info` tables |
| Add a new relationship type with metadata | **Medium** | Needs junction table, info table, ORM models, serialisers, views |
| Change the label hierarchy or add label attributes | **Medium** | Self-referential FK + cycle detection enforced in application code |
| Remove a core entity or merge two junction tables | **Hard** | 106 FKs, all `NO ACTION`, all managed in Python — breakage is wide |
| Enforce stricter data quality (add `NOT NULL`) | **Hard** | Existing data almost certainly contains NULLs; migration is painful |
| Fix the `itob.related_as` int vs array inconsistency | **Hard** | Touches serialisers, views, frontend, and existing stored data |

---

## Recommendations

### 1. Decide on a FK delete strategy

Either move appropriate relationships to `ON DELETE CASCADE` in the database, or
explicitly document which model owns each deletion path and enforce it with
integration tests. The current position — `NO ACTION` everywhere, managed in Python
— leaves the application carrying the full burden without a database safety net or
a clear contract.

### 2. Scope `actor_profile` to the deployment

If the deployment does not require forensic or missing-persons documentation,
consider whether the 50+ forensic columns belong in the schema or in a separate
optional module. Keeping them costs nothing at low data volumes but adds cognitive
load for every developer and generates unnecessary ORM overhead at scale.

### 3. Fix the `related_as` inconsistency

Align `itob.related_as` with the `ARRAY(integer)` pattern used by `atob` and
`itoa`, or document a deliberate reason for the difference. This should be done
before the API surface grows.

### 4. Consider lightweight data quality constraints

Even for a system that tolerates partial data, a small number of CHECK constraints
would catch common mistakes:

- `bulletin`: require at least one of `title` or `sjac_title` to be non-null
- `event`: require `from_date` to be non-null (an undated event is not useful)
- `geo_location`: require `latlng` to be non-null

These do not restrict data entry; they prevent accidentally blank records.

---

## Bottom line

**The architecture is sound and can be recommended as a professional structure.**

The core entity model is well-designed for the problem domain. The main maintenance
risk is not the schema complexity itself — it is the gap between what the database
enforces and what the application code assumes. Closing that gap incrementally,
starting with the three items above, will significantly improve long-term
maintainability.

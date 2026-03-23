# -*- coding: utf-8 -*-
"""
sample_data/sample_data_minimal_reset.py
=======================================
Minimal demo data seeder for Bayanat — always resets to a clean state.

PURPOSE
───────
Gives developers a single reproducible scenario they can restore in under
10 seconds: one bulletin, one actor, one incident, fully wired together
with reference data, labels, media, and a map pin.  Use it to:

  - Verify the UI after migrations or config changes
  - Check that reference-data changes (violations, event types, etc.) work
  - Start fresh without blowing away the whole database

FICTITIOUS SCENARIO
───────────────────
"Siege of Lewes Castle" — 17 March 2026
A crowd of ~200 people converged on Lewes Castle in East Sussex, England.
An image posted to X (Twitter) by a bystander is the single piece of
open-source evidence.  Actor "Thomas Ashdown" is identified in the image.

USAGE
─────
    uv run python sample_data/sample_data_minimal_reset.py

Must be run from the project root with the virtual environment active.
The Flask app context is created automatically by the __main__ block.

DESIGN NOTES
────────────
Label table:
    Label rows are content data (they belong to individual cases) but are
    seeded here because they are tied to individual cases and the entire
    label table is wiped by clear_all_content().  They are created inside
    seed_minimal() rather than replace_reference_data() for that reason.

    Two categories of label (controlled by Label.verified):
      Unverified (verified=False)  — descriptive, allegation-based;
                                     applied during initial triage
      Verified   (verified=True)   — neutral, evidence-based;
                                     applied during peer review

TRUNCATE vs ORM delete:
    clear_all_content() uses raw "TRUNCATE … CASCADE" rather than ORM
    .query.delete() calls.  This avoids having to know the exact
    FK-ordering of 30+ tables and is an order of magnitude faster.

_replace() / nullify pattern:
    reference-data tables that are foreign-keyed from content tables
    cannot simply be deleted — Postgres will raise an FK violation even
    after TRUNCATE if the reference rows were re-created with the same IDs
    and the content rows still reference them.  The nullify= parameter
    handles this by either:
      - SET NULL on the FK column (for nullable FKs), or
      - DELETE FROM the M2M association table (for compound PKs that
        cannot be nullified), passed as col="*".
    After nullification the old reference rows are deleted, then new rows
    are inserted.

WHAT THIS SCRIPT DOES (in order)
─────────────────────────────────
1. CLEAR all content  (clear_all_content)
   - Deletes any media files from disk (enferno/media/)
   - Runs TRUNCATE CASCADE on every content table

2. REPLACE all reference / lookup data  (replace_reference_data)
   Deletes every row in each lookup table, then inserts UK-appropriate
   values (English criminal offences, UK admin divisions, etc.).

   Table                 Rows  Notes
   ────────────────────  ────  ─────────────────────────────────────────
   PotentialViolation       9  Criminal offence categories (UK law)
   ClaimedViolation        15  Specific UK criminal charges
   Eventtype               19  Actor events (Arrested, Charged, Sentenced …)
                               + Bulletin events (Pre-Incident, Incident …)
   Country                 16  United Kingdom first, then major countries
   LocationAdminLevel       5  Country / County / Town / District / Ward
   GeoLocationType         13  Historic Monument, Government Building, …
   MediaCategory           10  Photo, Video, Social Media Post, …
   AtobInfo                 7  Actor↔Bulletin relationship types
   BtobInfo                 9  Bulletin↔Bulletin
   AtoaInfo                15  Actor↔Actor (incl. Co-accused)
   ItoaInfo                 7  Incident↔Actor
   ItobInfo                 4  Incident↔Bulletin
   ItoiInfo                 4  Incident↔Incident
   IDNumberType             7  National Insurance No, Passport, etc.

3. SEED minimal demo content  (seed_minimal)

   Entity       Count  Detail
   ───────────  ─────  ──────────────────────────────────────────────────
   Sources         10  X (Twitter), BBC News, Sussex Police, The Guardian,
                       ITV News, Sky News, Instagram, Facebook, YouTube,
                       Witness Statement
   Locations        3  East Sussex → Lewes → Lewes Castle
   Labels          13  7 verified (neutral, evidence-based) +
                       6 unverified (descriptive, allegation-based)
   Actors           1  Fictional: "Thomas Ashdown" — photographed in crowd
   Bulletins        5  X post, Facebook caption, Instagram caption, TikTok
                       caption, eyewitness statement (Margaret Okafor) —
                       each with labels, verified labels, tags;
                       X post also has event and map pin
   Incident         1  "Siege of Lewes Castle (17 March 2026)"
   Atob link        1  Ashdown ↔ bulletin (Appeared)
   Itob link        1  Incident ↔ bulletin (Primary Evidence)
   Itoa link        1  Incident ↔ Ashdown (Participant)
   Media            1  lewes-castle.png (stand-in for the X post image)
"""

from datetime import datetime
from pathlib import Path
from uuid import uuid4

from enferno.extensions import db
from enferno.admin.models import (
    Bulletin, Actor, Incident, Location, Event, Source, Label,
    Eventtype, Country, PotentialViolation, ClaimedViolation,
    LocationAdminLevel, LocationType, GeoLocationType, WorkflowStatus,
    Atob, Itob, Itoa, Media, GeoLocation,
)
from enferno.admin.models.ActorProfile import ActorProfile
from enferno.admin.models.AtobInfo import AtobInfo
from enferno.admin.models.BtobInfo import BtobInfo
from enferno.admin.models.AtoaInfo import AtoaInfo
from enferno.admin.models.ItobInfo import ItobInfo
from enferno.admin.models.ItoaInfo import ItoaInfo
from enferno.admin.models.ItoiInfo import ItoiInfo
from enferno.admin.models.MediaCategory import MediaCategory
from enferno.admin.models.IDNumberType import IDNumberType
from enferno.user.models import User
from flask_security.utils import hash_password


def _dt(year, month, day, hour=0, minute=0):
    return datetime(year, month, day, hour, minute)


# ─── Reference data replacement ────────────────────────────────────────


def replace_reference_data():
    """Replace all reference/lookup data with US-appropriate values."""
    from sqlalchemy import text

    print("Replacing reference data...")

    def _replace(model, rows, nullify=None):
        """Delete all rows and insert new ones.

        Args:
            nullify: list of (table, column) strings to SET NULL before
                     deleting, to avoid FK violations.
                     e.g. [("event", "eventtype_id")]
        """
        for table, col in (nullify or []):
            db.session.execute(text(f"DELETE FROM {table}") if col == "*"
                               else text(f"UPDATE {table} SET {col} = NULL"))
        db.session.flush()
        db.session.execute(text(f"TRUNCATE TABLE {model.__tablename__} RESTART IDENTITY CASCADE"))
        db.session.flush()
        for row in rows:
            db.session.add(model(**row))
        db.session.flush()
        print(f"  {model.__name__}: {len(rows)} entries")

    # ── Potential Violations (incident_potential_violations M2M → potential_violation)
    _replace(PotentialViolation, [
        {"id": 1, "title": "Criminal Offence"},
        {"id": 2, "title": "Public Order Offence"},
        {"id": 3, "title": "Violent Disorder"},
        {"id": 4, "title": "Criminal Damage"},
        {"id": 5, "title": "Assault"},
        {"id": 6, "title": "Trespass"},
        {"id": 7, "title": "Heritage Crime"},
        {"id": 8, "title": "Not a violation"},
        {"id": 9, "title": "Unknown"},
    ], nullify=[("incident_potential_violations", "*")])

    # ── Claimed Violations (incident_claimed_violations M2M → claimed_violation)
    _replace(ClaimedViolation, [
        {"id": 1, "title": "Violent disorder (Public Order Act 1986, s.2)"},
        {"id": 2, "title": "Riot (Public Order Act 1986, s.1)"},
        {"id": 3, "title": "Affray (Public Order Act 1986, s.3)"},
        {"id": 4, "title": "Threatening behaviour (Public Order Act 1986, s.4)"},
        {"id": 5, "title": "Criminal damage (Criminal Damage Act 1971, s.1)"},
        {"id": 6, "title": "Arson (Criminal Damage Act 1971, s.1(3))"},
        {"id": 7, "title": "Assault on emergency worker (Assaults on Emergency Workers Act 2018)"},
        {"id": 8, "title": "ABH — Actual Bodily Harm (OAPA 1861, s.47)"},
        {"id": 9, "title": "GBH — Grievous Bodily Harm (OAPA 1861, s.18/s.20)"},
        {"id": 10, "title": "Aggravated trespass (Criminal Justice and Public Order Act 1994, s.68)"},
        {"id": 11, "title": "Conspiracy to commit criminal damage"},
        {"id": 12, "title": "Possession of offensive weapon (Prevention of Crime Act 1953)"},
        {"id": 13, "title": "Theft (Theft Act 1968, s.1)"},
        {"id": 14, "title": "Burglary (Theft Act 1968, s.9)"},
        {"id": 15, "title": "Encouraging or assisting crime (Serious Crime Act 2007)"},
    ], nullify=[("incident_claimed_violations", "*")])

    # ── Event Types (Event.eventtype_id → eventtype)
    _replace(Eventtype, [
        {"id": 10, "title": "Birth", "for_actor": True, "for_bulletin": False},
        {"id": 11, "title": "Death", "for_actor": True, "for_bulletin": False},
        {"id": 12, "title": "Arrested", "for_actor": True, "for_bulletin": False},
        {"id": 13, "title": "Released", "for_actor": True, "for_bulletin": False},
        {"id": 14, "title": "Charged", "for_actor": True, "for_bulletin": False},
        {"id": 15, "title": "Convicted", "for_actor": True, "for_bulletin": False},
        {"id": 16, "title": "Sentenced", "for_actor": True, "for_bulletin": False},
        {"id": 17, "title": "Acquitted", "for_actor": True, "for_bulletin": False},
        {"id": 18, "title": "Pardoned", "for_actor": True, "for_bulletin": False},
        {"id": 19, "title": "Wounded", "for_actor": True, "for_bulletin": False},
        {"id": 20, "title": "Testified", "for_actor": True, "for_bulletin": False},
        {"id": 21, "title": "Plea Deal", "for_actor": True, "for_bulletin": False},
        {"id": 22, "title": "Trial", "for_actor": True, "for_bulletin": False},
        {"id": 23, "title": "Sighting", "for_actor": True, "for_bulletin": False},
        {"id": 24, "title": "Other", "for_actor": True, "for_bulletin": False},
        {"id": 29, "title": "Pre-Incident", "for_actor": False, "for_bulletin": True},
        {"id": 30, "title": "Incident", "for_actor": False, "for_bulletin": True},
        {"id": 31, "title": "Post-Incident", "for_actor": False, "for_bulletin": True},
        {"id": 32, "title": "Publication", "for_actor": False, "for_bulletin": True},
    ], nullify=[("event", "eventtype_id")])

    # ── Countries (Location.country_id, actor_countries.country_id → countries)
    _replace(Country, [
        {"id": 1, "title": "United Kingdom"},
        {"id": 2, "title": "France"},
        {"id": 3, "title": "Germany"},
        {"id": 4, "title": "Ireland"},
        {"id": 5, "title": "United States"},
        {"id": 6, "title": "Australia"},
        {"id": 7, "title": "Canada"},
        {"id": 8, "title": "India"},
        {"id": 9, "title": "Poland"},
        {"id": 10, "title": "Romania"},
        {"id": 11, "title": "Italy"},
        {"id": 12, "title": "Spain"},
        {"id": 13, "title": "Netherlands"},
        {"id": 14, "title": "Pakistan"},
        {"id": 15, "title": "Nigeria"},
        {"id": 16, "title": "Other"},
    ], nullify=[("location", "country_id"), ("actor_countries", "*")])

    # ── Administrative Divisions (Location.admin_level_id → location_admin_level)
    _replace(LocationAdminLevel, [
        {"id": 1, "code": 1, "title": "Country"},
        {"id": 2, "code": 2, "title": "County"},
        {"id": 3, "code": 3, "title": "Town"},
        {"id": 4, "code": 4, "title": "District"},
        {"id": 5, "code": 5, "title": "Ward"},
    ], nullify=[("location", "admin_level_id")])

    # ── GeoLocation Types (geo_location.type_id → geo_location_types)
    _replace(GeoLocationType, [
        {"id": 1, "title": "Historic Monument"},
        {"id": 2, "title": "Government Building"},
        {"id": 3, "title": "Police Station"},
        {"id": 4, "title": "Court/Judicial Building"},
        {"id": 5, "title": "Hospital/Medical Facility"},
        {"id": 6, "title": "Educational Institution"},
        {"id": 7, "title": "Religious Structure"},
        {"id": 8, "title": "Transport Hub"},
        {"id": 9, "title": "Public Park/Garden"},
        {"id": 10, "title": "Hotel/Lodging"},
        {"id": 11, "title": "Commercial/Retail"},
        {"id": 12, "title": "Residential"},
        {"id": 13, "title": "Infrastructure"},
    ], nullify=[("geo_location", "type_id")])

    # ── Media Categories
    _replace(MediaCategory, [
        {"id": 1, "title": "Photo"},
        {"id": 2, "title": "Video"},
        {"id": 3, "title": "Audio"},
        {"id": 4, "title": "Document"},
        {"id": 5, "title": "Social Media Post"},
        {"id": 6, "title": "Court Filing"},
        {"id": 7, "title": "Body Camera Footage"},
        {"id": 8, "title": "Security Camera Footage"},
        {"id": 9, "title": "News Report"},
        {"id": 10, "title": "Satellite/Aerial Imagery"},
    ])

    # ── Relationship Types
    _replace(AtobInfo, [
        {"id": 1, "title": "Injured Party"},
        {"id": 2, "title": "Witness"},
        {"id": 3, "title": "Perpetrator"},
        {"id": 4, "title": "Appeared"},
        {"id": 5, "title": "Participant"},
        {"id": 6, "title": "Subject"},
        {"id": 7, "title": "Other"},
    ])

    _replace(BtobInfo, [
        {"id": 1, "title": "Duplicate"},
        {"id": 2, "title": "Other"},
        {"id": 3, "title": "Part of a Series"},
        {"id": 4, "title": "Same Event"},
        {"id": 5, "title": "Same Person"},
        {"id": 6, "title": "Potentially Duplicate"},
        {"id": 7, "title": "Potentially Related"},
        {"id": 8, "title": "Corroborates"},
        {"id": 9, "title": "Contradicts"},
    ])

    _replace(AtoaInfo, [
        {"id": 1, "title": "Same Person", "reverse_title": "Same Person"},
        {"id": 2, "title": "Duplicate", "reverse_title": "Duplicate"},
        {"id": 3, "title": "Parent", "reverse_title": "Child"},
        {"id": 4, "title": "Child", "reverse_title": "Parent"},
        {"id": 5, "title": "Sibling", "reverse_title": "Sibling"},
        {"id": 6, "title": "Spouse", "reverse_title": "Spouse"},
        {"id": 7, "title": "Superior", "reverse_title": "Subordinate"},
        {"id": 8, "title": "Subordinate", "reverse_title": "Superior"},
        {"id": 9, "title": "Associate", "reverse_title": "Associate"},
        {"id": 10, "title": "Alleged Perpetrator", "reverse_title": "Victim"},
        {"id": 11, "title": "Member", "reverse_title": "Group"},
        {"id": 12, "title": "Group", "reverse_title": "Member"},
        {"id": 13, "title": "Co-accused", "reverse_title": "Co-accused"},
        {"id": 14, "title": "Other", "reverse_title": "Other"},
        {"id": 15, "title": "Victim", "reverse_title": "Alleged Perpetrator"},
    ])

    _replace(ItoaInfo, [
        {"id": 1, "title": "Injured Party"},
        {"id": 2, "title": "Witness"},
        {"id": 3, "title": "Perpetrator"},
        {"id": 4, "title": "Appeared"},
        {"id": 5, "title": "Participant"},
        {"id": 6, "title": "Responding Officer"},
        {"id": 7, "title": "Other"},
    ])

    _replace(ItobInfo, [
        {"id": 1, "title": "Default"},
        {"id": 2, "title": "Primary Evidence"},
        {"id": 3, "title": "Supporting Evidence"},
        {"id": 4, "title": "Context"},
    ])

    _replace(ItoiInfo, [
        {"id": 1, "title": "Default"},
        {"id": 2, "title": "Part of"},
        {"id": 3, "title": "Led to"},
        {"id": 4, "title": "Related"},
    ])

    _replace(IDNumberType, [
        {"id": 1, "title": "National Insurance Number"},
        {"id": 2, "title": "Driving Licence"},
        {"id": 3, "title": "Passport"},
        {"id": 4, "title": "Crown Court Case Number"},
        {"id": 5, "title": "Police National Computer ID"},
        {"id": 6, "title": "NHS Number"},
        {"id": 7, "title": "Crime Reference Number"},
    ])

    db.session.commit()
    print("Reference data replaced successfully!")


# ─── Clear all content data ───────────────────────────────────────────


def clear_all_content():
    """Wipe all content tables (bulletins, actors, incidents, etc.) via TRUNCATE CASCADE."""
    from sqlalchemy import text

    print("Clearing all content data...")

    # Delete media files from disk before truncating
    for m in Media.query.all():
        filepath = Media.media_dir / m.media_file
        if filepath.exists():
            filepath.unlink()
            print(f"  Deleted file: {m.media_file}")

    # TRUNCATE CASCADE handles FK ordering for us
    content_tables = [
        "atob", "btob", "itob", "itoa", "atoa", "itoi",          # relationships
        "media", "geo_location", "actor_profile",                     # dependent records
        "bulletin_events", "actor_events", "incident_events",      # M2M event links
        "bulletin_sources", "bulletin_locations",                   # M2M bulletin
        "bulletin_labels", "bulletin_verlabels", "bulletin_roles",
        "actor_roles", "actor_countries", "actor_labels",           # M2M actor
        "actor_sources", "actor_verlabels",
        "actor_dialects", "actor_ethnographies",
        "incident_locations", "incident_labels", "incident_roles",  # M2M incident
        "incident_potential_violations", "incident_claimed_violations",
        "event",                                                    # events
        "bulletin", "actor", "incident",                            # main entities
        "location", "source", "label",                              # supporting
    ]

    db.session.execute(text(
        "TRUNCATE TABLE " + ", ".join(content_tables) + " RESTART IDENTITY CASCADE"
    ))
    db.session.commit()
    print("All content data cleared.")


# ─── Seed minimal demo data ────────────────────────────────────────────


def seed_minimal():
    """Seed the Lewes Castle siege scenario: 1 incident, 1 bulletin, 1 actor."""

    from enferno.user.models import Role
    admin = User.query.join(User.roles).filter(Role.name == "Admin").first()
    if not admin:
        print("Error: No admin user found. Run 'flask install' first.")
        return False

    print("Seeding minimal demo data...")

    # ── Test users ──────────────────────────────────────────────────
    da_role = Role.query.filter_by(name="DA").first()

    # Delete all non-admin users so we start fresh each run
    non_admin_users = User.query.filter(~User.roles.any(Role.name == "Admin")).all()
    for u in non_admin_users:
        db.session.delete(u)
    db.session.flush()
    if non_admin_users:
        print(f"  Deleted {len(non_admin_users)} non-admin user(s)")

    test_user_defs = [
        ("user1", "User One",   "user1@demo.local"),
        ("user2", "User Two",   "user2@demo.local"),
        ("user3", "User Three", "user3@demo.local"),
    ]
    test_users = {}
    for uname, display, email in test_user_defs:
        u = User.query.filter_by(username=uname).first()
        u = User(
            username=uname,
            name=display,
            email=email,
            password=hash_password(f"{uname}pass"),
            active=True,
            fs_uniquifier=uuid4().hex,
        )
        if da_role:
            u.roles.append(da_role)
        db.session.add(u)
        db.session.flush()
        print(f"  Created test user: {uname} / {uname}pass (DA)")
        test_users[uname] = u
    user1 = test_users["user1"]

    # ── Reference lookups ───────────────────────────────────────────
    loc_type_admin = LocationType.query.filter_by(title="Administrative Location").first()
    loc_type_poi = LocationType.query.filter_by(title="Point of Interest").first()
    admin_level = {al.title: al for al in LocationAdminLevel.query.all()}
    wf_reviewed = WorkflowStatus.query.filter_by(title="Peer Reviewed").first()
    wf_assigned = WorkflowStatus.query.filter_by(title="Assigned").first()
    status = wf_reviewed.title if wf_reviewed else "Peer Reviewed"
    status_assigned = wf_assigned.title if wf_assigned else "Assigned"
    evt_types = {et.title: et for et in Eventtype.query.all()}
    pv = {v.title: v for v in PotentialViolation.query.all()}
    cv = {v.title: v for v in ClaimedViolation.query.all()}

    from geoalchemy2.shape import from_shape
    from shapely.geometry import Point

    # ── Sources ─────────────────────────────────────────────────────
    source_titles = [
        "X (Twitter)",
        "BBC News",
        "Sussex Police",
        "The Guardian",
        "ITV News",
        "Sky News",
        "Instagram",
        "Facebook",
        "YouTube",
        "Witness Statement",
        "TikTok",
    ]
    sources = {}
    for title in source_titles:
        s = Source(title=title)
        db.session.add(s)
        sources[title] = s
    db.session.flush()

    src = sources["X (Twitter)"]  # used for the bulletin below

    # ── Location hierarchy ──────────────────────────────────────────
    uk = Country.query.filter_by(title="United Kingdom").first()

    east_sussex = Location(
        title="East Sussex",
        location_type_id=loc_type_admin.id if loc_type_admin else None,
        admin_level_id=admin_level.get("County").id if admin_level.get("County") else None,
        country_id=uk.id if uk else None,
    )
    east_sussex.latlng = from_shape(Point(0.2715, 50.9100), srid=4326)
    db.session.add(east_sussex)
    db.session.flush()

    lewes = Location(
        title="Lewes",
        location_type_id=loc_type_admin.id if loc_type_admin else None,
        admin_level_id=admin_level.get("Town").id if admin_level.get("Town") else None,
        country_id=uk.id if uk else None,
        parent_id=east_sussex.id,
    )
    lewes.latlng = from_shape(Point(-0.0083, 50.8748), srid=4326)
    db.session.add(lewes)
    db.session.flush()

    castle = Location(
        title="Lewes Castle",
        location_type_id=loc_type_poi.id if loc_type_poi else None,
        country_id=uk.id if uk else None,
        parent_id=lewes.id,
    )
    castle.latlng = from_shape(Point(-0.0083, 50.8748), srid=4326)
    db.session.add(castle)
    db.session.flush()

    # Populate denormalised columns used by the UI for hierarchy display and search.
    # full_location: human-readable hierarchy path shown in the UI.
    # id_tree:       space-separated "[id]" tokens used by location autocomplete.
    # Both are computed by recursive CTEs on the DB side, but those use a
    # separate connection and can't see uncommitted rows.  For a small fixed
    # set we set them directly from the known hierarchy.
    east_sussex.full_location = "East Sussex"
    east_sussex.id_tree = f"[{east_sussex.id}]"

    lewes.full_location = "Lewes, East Sussex"
    lewes.id_tree = f"[{lewes.id}] [{east_sussex.id}]"

    castle.full_location = "Lewes Castle, Lewes, East Sussex"
    castle.id_tree = f"[{castle.id}] [{lewes.id}] [{east_sussex.id}]"

    db.session.flush()

    # ── Labels (seed a small set — the label table was truncated) ──
    #
    # Unverified labels (verified=False):
    #   Descriptive labels based on observations and source allegations.
    #   Applied during initial triage — what the source claims or what the
    #   content appears to depict at first glance.
    #
    # Verified labels (verified=True):
    #   Neutral labels based on analyst observation and evidence.
    #   Applied during peer review — objective, factual classifications
    #   confirmed by an analyst reviewing the material.
    #
    label_defs = [
        # ── Verified labels (neutral, evidence-based) ────────────────
        {"title": "Image", "order": 100, "verified": True,
         "for_bulletin": True, "for_actor": False, "for_incident": False},
        {"title": "Social Media Post", "order": 101, "verified": True,
         "for_bulletin": True, "for_actor": False, "for_incident": False},
        {"title": "Outdoor Scene", "order": 102, "verified": True,
         "for_bulletin": True, "for_actor": False, "for_incident": False},
        {"title": "Multiple Persons Visible", "order": 103, "verified": True,
         "for_bulletin": True, "for_actor": False, "for_incident": False},
        {"title": "Historic Structure Visible", "order": 104, "verified": True,
         "for_bulletin": True, "for_actor": False, "for_incident": False},
        {"title": "Priority", "order": 105, "verified": True,
         "for_bulletin": True, "for_actor": True, "for_incident": True},
        {"title": "Graphic Content", "order": 106, "verified": True,
         "for_bulletin": True, "for_actor": True, "for_incident": True},
        # ── Unverified labels (descriptive, allegation-based) ────────
        {"title": "Protest / Demonstration", "order": 300, "verified": False,
         "for_bulletin": True, "for_actor": False, "for_incident": True},
        {"title": "Siege / Occupation", "order": 301, "verified": False,
         "for_bulletin": True, "for_actor": False, "for_incident": True},
        {"title": "Property Damage Alleged", "order": 302, "verified": False,
         "for_bulletin": True, "for_actor": False, "for_incident": True},
        {"title": "Crowd / Gathering", "order": 303, "verified": False,
         "for_bulletin": True, "for_actor": False, "for_incident": True},
        {"title": "Heritage Site Threatened", "order": 304, "verified": False,
         "for_bulletin": True, "for_actor": False, "for_incident": True},
        {"title": "Trespass Alleged", "order": 305, "verified": False,
         "for_bulletin": True, "for_actor": False, "for_incident": True},
    ]
    label_map = {}
    for ldef in label_defs:
        lbl = Label(
            title=ldef["title"],
            order=ldef["order"],
            verified=ldef["verified"],
            for_bulletin=ldef["for_bulletin"],
            for_actor=ldef["for_actor"],
            for_incident=ldef["for_incident"],
        )
        db.session.add(lbl)
        db.session.flush()
        label_map[ldef["title"]] = lbl

    # ── Actor ───────────────────────────────────────────────────────
    a = Actor()
    a.name = "Thomas Ashdown"
    a.first_name = "Thomas"
    a.last_name = "Ashdown"
    a.sex = "Male"
    a.age = "Adult 18+"
    a.civilian = "Civilian"
    a.type = "Person"
    a.comments = (
        "Identified in social media imagery at the front of the crowd "
        "outside Lewes Castle on 17 March 2026. Seen carrying a placard "
        "and shouting through a megaphone. Resident of Lewes."
    )
    a.status = status
    a.tags = ["suspect", "lewes resident"]
    a.id_number = []
    db.session.add(a)
    db.session.flush()

    profile = ActorProfile(actor_id=a.id, mode=2)
    profile.description = a.comments
    db.session.add(profile)

    # ── Bulletin ────────────────────────────────────────────────────
    b = Bulletin()
    # title: original source wording (the tweet text as posted)
    b.title = "Unbelievable scenes at Lewes Castle right now. Hundreds here. #LewesCastle"
    # sjac_title: analyst's normalised title
    b.sjac_title = "X post: crowd gathered at Lewes Castle gate - 17 Mar 2026"
    b.description = (
        "Image posted to X (formerly Twitter) by @lewes_observer at 14:22 GMT "
        "on 17 March 2026. Shows approximately 200 people gathered at the "
        "barbican entrance to Lewes Castle. Several individuals are carrying "
        "placards. Smoke visible in the background near the castle keep. "
        "Post received 4,300 retweets before the account was suspended."
    )
    b.originid = "1234567890"       # tweet ID extracted from source URL
    b.source_link = "https://x.com/lewes_observer/status/1234567890"
    b.publish_date = _dt(2026, 3, 17, 14, 22)
    b.documentation_date = _dt(2026, 3, 17, 16, 0)
    b.reliability_score = 40        # unverified account; no corroboration yet
    b.comments = (
        "Source account @lewes_observer has no prior history. Image metadata "
        "not yet verified. Account was suspended shortly after posting — "
        "screenshot preserved as evidence. Awaiting corroboration from news sources."
    )
    b.status = status_assigned
    b.user_id = admin.id
    b.assigned_to_id = user1.id
    b.tags = [
        "Lewes", "castle siege", "protest", "crowd", "X post",
        "East Sussex", "open source",
    ]
    db.session.add(b)
    db.session.flush()

    # Unverified labels: descriptive, based on what the source alleges or
    # what the content appears to show at first glance
    for key in ["Crowd / Gathering", "Heritage Site Threatened",
                "Siege / Occupation", "Protest / Demonstration"]:
        lbl = label_map.get(key)
        if lbl:
            b.labels.append(lbl)

    # Verified labels: neutral, factual classifications confirmed by an
    # analyst reviewing the material
    for key in ["Social Media Post", "Image", "Outdoor Scene",
                "Multiple Persons Visible", "Historic Structure Visible", "Priority"]:
        lbl = label_map.get(key)
        if lbl:
            b.ver_labels.append(lbl)

    b.locations.append(castle)
    b.sources.append(src)

    # ── GeoLocation (map marker) ──────────────────────────────────
    geo_type_hist = GeoLocationType.query.filter_by(title="Historic Monument").first()

    geo = GeoLocation()
    geo.title = "Lewes Castle"
    geo.latlng = "POINT(-0.0083 50.8748)"
    geo.type_id = geo_type_hist.id if geo_type_hist else None
    geo.main = True
    geo.comment = "11th-century Norman castle. Crowd gathered at the barbican gate."
    geo.bulletin_id = b.id
    db.session.add(geo)
    db.session.flush()

    # ── Bulletin event ──────────────────────────────────────────────
    et = evt_types.get("Incident")
    evt = Event(
        title="Crowd gathers at Lewes Castle barbican",
        eventtype_id=et.id if et else None,
        from_date=_dt(2026, 3, 17, 13, 30),
        to_date=_dt(2026, 3, 17, 17, 0),
        location_id=castle.id,
    )
    db.session.add(evt)
    db.session.flush()
    b.events.append(evt)

    # ── Facebook bulletin ───────────────────────────────────────────
    b_fb = Bulletin()
    # title: the caption as posted on Facebook
    b_fb.title = (
        "Just drove past Lewes Castle and there are hundreds of people outside! "
        "Never seen anything like it. Police everywhere. Stay safe everyone ❤️ "
        "#Lewes #LewesCastle"
    )
    b_fb.sjac_title = "Facebook post: eyewitness reports crowd at Lewes Castle - 17 Mar 2026"
    b_fb.description = (
        "Public Facebook post by user 'Sandra Brightwell' at 14:35 GMT on "
        "17 March 2026. Post accompanied by a photograph taken from a car window "
        "showing police vehicles and a large crowd on the approach road to "
        "Lewes Castle. Post received 312 shares and 890 reactions before the "
        "account was set to private."
    )
    b_fb.originid = "FB-10158234567890"
    b_fb.source_link = "https://www.facebook.com/permalink.php?story_fbid=10158234567890"
    b_fb.publish_date = _dt(2026, 3, 17, 14, 35)
    b_fb.documentation_date = _dt(2026, 3, 17, 17, 30)
    b_fb.reliability_score = 50
    b_fb.comments = (
        "Account appears to be a genuine local resident based on post history. "
        "Photograph shows police vehicles consistent with a major incident response. "
        "Account set to private shortly after — screenshot and metadata preserved."
    )
    b_fb.status = status_assigned
    b_fb.user_id = admin.id
    b_fb.assigned_to_id = test_users["user2"].id
    b_fb.tags = ["Lewes", "castle siege", "Facebook", "eyewitness", "crowd", "East Sussex"]
    db.session.add(b_fb)
    db.session.flush()

    for key in ["Crowd / Gathering", "Protest / Demonstration"]:
        lbl = label_map.get(key)
        if lbl:
            b_fb.labels.append(lbl)
    for key in ["Image", "Social Media Post", "Outdoor Scene", "Multiple Persons Visible"]:
        lbl = label_map.get(key)
        if lbl:
            b_fb.ver_labels.append(lbl)
    b_fb.locations.append(castle)
    b_fb.sources.append(sources["Facebook"])

    # ── Instagram bulletin ──────────────────────────────────────────
    b_ig = Bulletin()
    # title: the Instagram caption as posted
    b_ig.title = (
        "History under siege 🏰 Incredible and frightening scenes unfolding right "
        "now at Lewes Castle. This place has stood for 900 years. "
        "#LewesCastle #Lewes #EastSussex #protest #history"
    )
    b_ig.sjac_title = "Instagram post: photograph of crowd at Lewes Castle barbican - 17 Mar 2026"
    b_ig.description = (
        "Public Instagram post by account @historic_lewes at 14:41 GMT on "
        "17 March 2026. Post contains a single high-resolution photograph taken "
        "from an elevated position (possibly the adjacent bowling green) showing "
        "the full scale of the crowd at the barbican entrance. Castle keep visible "
        "in the background with smoke rising from the east side. "
        "Post received 2,100 likes and 340 comments before the account was archived."
    )
    b_ig.originid = "3012345678901234567"
    b_ig.source_link = "https://www.instagram.com/p/C4xAbCdEfGh/"
    b_ig.publish_date = _dt(2026, 3, 17, 14, 41)
    b_ig.documentation_date = _dt(2026, 3, 17, 18, 0)
    b_ig.reliability_score = 55
    b_ig.comments = (
        "Elevated angle provides better crowd size assessment than ground-level images. "
        "Smoke visible near east keep — consistent with damage reported in police statement. "
        "Account @historic_lewes has a prior history of local heritage photography, "
        "increasing source credibility. Image metadata not yet verified."
    )
    b_ig.status = status_assigned
    b_ig.user_id = admin.id
    b_ig.assigned_to_id = test_users["user3"].id
    b_ig.tags = ["Lewes", "castle siege", "Instagram", "aerial view", "smoke", "East Sussex", "heritage"]
    db.session.add(b_ig)
    db.session.flush()

    for key in ["Siege / Occupation", "Heritage Site Threatened", "Property Damage Alleged"]:
        lbl = label_map.get(key)
        if lbl:
            b_ig.labels.append(lbl)
    for key in ["Image", "Social Media Post", "Outdoor Scene", "Multiple Persons Visible",
                "Historic Structure Visible", "Priority"]:
        lbl = label_map.get(key)
        if lbl:
            b_ig.ver_labels.append(lbl)
    b_ig.locations.append(castle)
    b_ig.sources.append(sources["Instagram"])

    # ── TikTok bulletin ─────────────────────────────────────────────
    b_tt = Bulletin()
    # title: the TikTok caption as posted (short, hashtag-heavy)
    b_tt.title = "POV: you're at lewes castle rn 😳 #lewes #lewestok #fyp #castle #siege #uk"
    b_tt.sjac_title = "TikTok video: interior footage of crowd inside Lewes Castle grounds - 17 Mar 2026"
    b_tt.description = (
        "TikTok video posted by account @sussex_daily at 15:04 GMT on "
        "17 March 2026. 47-second handheld video filmed from inside the castle "
        "grounds after the barbican gate was breached. Footage shows a large crowd "
        "moving through the outer ward toward the keep, with audible shouting. "
        "At 0:23 a section of decorative stonework is visible with fresh damage. "
        "Video reached 1.4 million views before removal by TikTok at 19:30 GMT. "
        "Archived copy preserved by documentation team."
    )
    b_tt.originid = "7312345678901234567"
    b_tt.source_link = "https://www.tiktok.com/@sussex_daily/video/7312345678901234567"
    b_tt.publish_date = _dt(2026, 3, 17, 15, 4)
    b_tt.documentation_date = _dt(2026, 3, 17, 19, 45)
    b_tt.reliability_score = 65
    b_tt.comments = (
        "Only known video from inside the castle grounds after the breach. "
        "Stonework damage visible at 0:23 corroborates the curator's statement. "
        "Video removed by TikTok — archived copy held. Account @sussex_daily "
        "has 18k followers and a history of local news coverage. "
        "Geolocation via background landmarks confirmed as inner ward of Lewes Castle."
    )
    b_tt.status = status_assigned
    b_tt.user_id = admin.id
    b_tt.assigned_to_id = test_users["user1"].id
    b_tt.tags = ["Lewes", "castle siege", "TikTok", "interior", "video", "breach", "stonework damage"]
    db.session.add(b_tt)
    db.session.flush()

    for key in ["Siege / Occupation", "Property Damage Alleged", "Trespass Alleged"]:
        lbl = label_map.get(key)
        if lbl:
            b_tt.labels.append(lbl)
    for key in ["Social Media Post", "Outdoor Scene", "Multiple Persons Visible",
                "Historic Structure Visible", "Priority", "Graphic Content"]:
        lbl = label_map.get(key)
        if lbl:
            b_tt.ver_labels.append(lbl)
    b_tt.locations.append(castle)
    b_tt.sources.append(sources["TikTok"])

    # ── Eyewitness statement bulletin ──────────────────────────────
    b_ew = Bulletin()
    b_ew.title = (
        "Witness statement — Margaret Okafor, 17 March 2026. "
        "I was working in the castle ticket office when the crowd arrived."
    )
    b_ew.sjac_title = "Witness statement: castle ticket office staff member — 17 Mar 2026"
    b_ew.description = (
        "Written statement provided by Margaret Okafor, ticket office supervisor "
        "at Lewes Castle, taken by Sussex Police on 18 March 2026 (ref: SP-2026-0317-04). "
        "\n\n"
        "\"I was on duty in the ticket office at approximately 13:45 when I noticed a "
        "large number of people gathering outside the barbican gate. There were far more "
        "than would be typical for a Tuesday afternoon. I estimated two hundred or more. "
        "Some were carrying placards but I could not read them from my position. "
        "\n\n"
        "At around 14:05 the crowd surged forward. The gate, which had been left "
        "on the latch while a school group was exiting, was pushed open. I immediately "
        "called 999 and activated the site alarm. I then directed the school group — "
        "approximately 30 children aged 10-11 and three teachers — through the rear "
        "fire exit into Albion Street. "
        "\n\n"
        "As I was leaving I heard a loud cracking sound from the direction of the keep. "
        "I did not see what caused it. I did not see Thomas Ashdown personally but was "
        "shown a photograph by police and confirmed that a man matching his description "
        "was near the front of the crowd when the gate was breached. "
        "\n\n"
        "I have worked at the castle for eleven years and have never seen anything like "
        "this. The damage to the east wall of the keep was not there when I arrived for "
        "my shift at 09:00.\""
    )
    b_ew.originid = "SP-2026-0317-04"
    b_ew.publish_date = _dt(2026, 3, 18, 10, 30)
    b_ew.documentation_date = _dt(2026, 3, 18, 14, 0)
    b_ew.reliability_score = 80
    b_ew.comments = (
        "Primary eyewitness account from a credible source — on-site staff member "
        "with 11 years at the castle. Statement taken under caution by Sussex Police "
        "the day after the incident. Key value: confirms the gate breach mechanism, "
        "the presence of a school group, the timing of the keep damage, and places a "
        "person matching Ashdown's description at the front of the crowd. "
        "No corroboration needed — consistent with all other evidence."
    )
    b_ew.status = status_assigned
    b_ew.user_id = admin.id
    b_ew.assigned_to_id = test_users["user2"].id
    b_ew.tags = ["Lewes", "witness statement", "castle siege", "gate breach", "keep damage", "police statement"]
    db.session.add(b_ew)
    db.session.flush()

    for key in ["Siege / Occupation", "Property Damage Alleged", "Trespass Alleged"]:
        lbl = label_map.get(key)
        if lbl:
            b_ew.labels.append(lbl)
    for key in ["Priority"]:
        lbl = label_map.get(key)
        if lbl:
            b_ew.ver_labels.append(lbl)
    b_ew.locations.append(castle)
    b_ew.sources.append(sources["Witness Statement"])

    # ── Actor-to-Bulletin link ──────────────────────────────────────
    atob = Atob(actor_id=a.id, bulletin_id=b.id)
    atob.related_as = [4]  # Appeared
    atob.probability = 85
    atob.comment = "Ashdown visible at the front of the crowd in the X post image."
    atob.user_id = admin.id
    db.session.add(atob)
    db.session.flush()

    # ── Incident ────────────────────────────────────────────────────
    inc = Incident()
    inc.title = "Siege of Lewes Castle (17 March 2026)"
    inc.description = (
        "On 17 March 2026 a crowd of approximately 200 people converged on "
        "Lewes Castle in the town of Lewes, East Sussex. The group forced entry "
        "through the barbican gate at around 14:00 GMT and occupied the castle "
        "grounds. Police declared a major incident at 14:45. Minor "
        "damage was reported to the 11th-century Norman keep. The site was "
        "cleared by 18:30 following negotiation. Several arrests were made."
    )
    inc.status = status
    inc.assigned_to_id = test_users["user2"].id
    inc.first_peer_reviewer_id = test_users["user3"].id
    inc.second_peer_reviewer_id = test_users["user1"].id
    inc.comments = (
        "Incident confirmed via cross-referencing the X post image with BBC News "
        "and a police press release. Damage to the Norman keep confirmed by "
        "a statement issued by Dr. Sarah Mellor, site curator, on 18 March 2026. "
        "Three arrests confirmed by police. Incident closed and peer reviewed."
    )
    db.session.add(inc)
    db.session.flush()

    # Attach violations to incident
    for pv_title in ["Public Order Offence", "Criminal Damage", "Trespass"]:
        v = pv.get(pv_title)
        if v:
            inc.potential_violations.append(v)
    for cv_title in [
        "Violent disorder (Public Order Act 1986, s.2)",
        "Criminal damage (Criminal Damage Act 1971, s.1)",
        "Aggravated trespass (Criminal Justice and Public Order Act 1994, s.68)",
    ]:
        v = cv.get(cv_title)
        if v:
            inc.claimed_violations.append(v)

    inc.locations.append(castle)

    for key in ["Protest / Demonstration", "Property Damage Alleged",
                "Heritage Site Threatened", "Trespass Alleged"]:
        lbl = label_map.get(key)
        if lbl:
            inc.labels.append(lbl)

    # Incident event
    inc_evt = Event(
        title="Crowd forces entry through barbican gate",
        eventtype_id=et.id if et else None,
        from_date=_dt(2026, 3, 17, 14, 0),
        to_date=_dt(2026, 3, 17, 14, 30),
        location_id=castle.id,
    )
    db.session.add(inc_evt)
    db.session.flush()
    inc.events.append(inc_evt)

    # Incident-to-Bulletin link
    itob = Itob(incident_id=inc.id, bulletin_id=b.id)
    itob.related_as = 2  # Primary Evidence
    itob.probability = 95
    itob.comment = "X post image is the earliest known visual evidence of the crowd."
    itob.user_id = admin.id
    db.session.add(itob)

    # Incident-to-Bulletin links for Facebook, Instagram, TikTok, and eyewitness bulletins
    for new_b, rel_type, prob, comment in [
        (b_fb, 3, 60, "Facebook post corroborates police presence and crowd scale."),
        (b_ig, 3, 75, "Instagram photograph provides best available crowd-size evidence."),
        (b_tt, 2, 90, "TikTok video is only footage from inside the grounds — shows breach and damage."),
        (b_ew, 2, 90, "Eyewitness statement confirms gate breach, keep damage, and Ashdown's position."),
    ]:
        db.session.add(Itob(
            incident_id=inc.id,
            bulletin_id=new_b.id,
            related_as=rel_type,
            probability=prob,
            comment=comment,
            user_id=admin.id,
        ))
    db.session.flush()

    # Incident-to-Actor link
    itoa = Itoa(actor_id=a.id, incident_id=inc.id)
    itoa.related_as = [5]  # Participant
    itoa.probability = 85
    itoa.comment = "Ashdown identified as a participant in the siege."
    itoa.user_id = admin.id
    db.session.add(itoa)
    db.session.flush()

    # ── Media (Lewes Castle photo — stand-in for X post image) ─────
    from enferno.utils.data_helpers import get_file_hash

    media_dir = Media.media_dir
    media_dir.mkdir(parents=True, exist_ok=True)

    import shutil

    src_file = Path(__file__).parent / "lewes-castle.png"
    filename = "lewes-castle.png"
    filepath = media_dir / filename

    if not filepath.exists() and src_file.exists():
        shutil.copy2(src_file, filepath)
        print(f"  Copied {filename} to media directory")

    if filepath.exists():
        etag = get_file_hash(str(filepath))
        if not Media.query.filter(Media.etag == etag, Media.deleted.is_not(True)).first():
            media = Media()
            media.media_file = filename
            media.media_file_type = "image/png"
            media.title = "Crowd at Lewes Castle barbican gate — posted to X by @lewes_observer"
            media.comments = "Screenshot of X post by @lewes_observer, 17 March 2026 14:22 GMT"
            media.etag = etag
            cat_photo = MediaCategory.query.filter_by(title="Photo").first()
            if cat_photo:
                media.category_id = cat_photo.id
            media.main = True
            media.user_id = admin.id
            media.bulletin_id = b.id
            db.session.add(media)
    elif not src_file.exists():
        print(f"  Warning: {src_file} not found — no media attached")

    db.session.commit()

    print("Minimal demo data seeded successfully!")
    print(f"  Test users: user1/user1pass, user2/user2pass, user3/user3pass")
    print(f"  Sources:    {len(source_titles)} ({', '.join(source_titles)})")
    print(f"  Locations:  3 (East Sussex → Lewes → Lewes Castle)")
    print(f"  Actors:     1 (Thomas Ashdown)")
    print(f"  Bulletins:  5")
    print(f"    - X post (assigned user1)")
    print(f"    - Facebook caption (assigned user2)")
    print(f"    - Instagram caption (assigned user3)")
    print(f"    - TikTok caption (assigned user1)")
    print(f"    - Eyewitness statement / Margaret Okafor (assigned user2)")
    print(f"  Incidents:  1 (Siege of Lewes Castle)")
    print(f"  Media:      1 (castle photo)")
    return True


# ─── Main ───────────────────────────────────────────────────────────────


if __name__ == "__main__":
    from enferno.app import create_app

    app = create_app()
    with app.app_context():
        clear_all_content()
        replace_reference_data()
        seed_minimal()

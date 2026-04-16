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

    Labels are organised in two groups:
      Classification labels  — descriptive, allegation-based (Protest /
                               Demonstration, Siege / Occupation, etc.)
      Investigation labels   — hierarchical tree rooted at "Investigations",
                               e.g. Investigations > Lewes Castle Siege >
                               Precursor / Protest / Assembly / Arrests

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
   Sources         10  X (Twitter), Albion Broadcasting, Lewes & Weald Constabulary, The National Courier,
                       ITV News, Sky News, Instagram, Facebook, YouTube,
                       Witness Statement
   Locations        9  East Sussex → Lewes → Lewes Castle
                              → Lewes Crown Court
                              → Lewes Police Station
                              → HM Prison Lewes
                          → Brighton
                          → Eastbourne
                          → Hastings
   Labels           9  6 classification labels (Protest, Siege, etc.) +
                       3 investigation labels (Investigations > Lewes Castle
                       Siege, Brighton Dome Rally)
   Actors           1  Fictional: "Thomas Ashdown" — photographed in crowd
   Bulletins        5  X post, Facebook caption, Instagram caption, TikTok
                       caption, eyewitness statement (Margaret Okafor) —
                       each with labels and investigation tags;
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
    Atob, Atoa, Itob, Itoa, Itoi, Media, GeoLocation,
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
from enferno.admin.models.DynamicField import DynamicField
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

    # ── Workflow Statuses (Bulletin.status, Actor.status, Incident.status use string values)
    _replace(WorkflowStatus, [
        {"id": 1, "title": "Machine Created", "title_tr": "Machine Created"},
        {"id": 2, "title": "Human Created", "title_tr": "Human Created"},
        {"id": 3, "title": "Updated", "title_tr": "Updated"},
        {"id": 4, "title": "Peer Reviewed", "title_tr": "Peer Reviewed"},
        {"id": 5, "title": "Finalized", "title_tr": "Finalized"},
        {"id": 6, "title": "Senior Reviewed", "title_tr": "Senior Reviewed"},
        {"id": 7, "title": "Machine Updated", "title_tr": "Machine Updated"},
        {"id": 8, "title": "Assigned", "title_tr": "Assigned"},
        {"id": 9, "title": "Second Peer Review", "title_tr": "Second Peer Review"},
        {"id": 10, "title": "Revisited", "title_tr": "Revisited"},
        {"id": 11, "title": "Senior Updated", "title_tr": "Senior Updated"},
        {"id": 12, "title": "Peer Review Assigned", "title_tr": "Peer Review Assigned"},
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

    # ── OVRM ID custom field ─────────────────────────────────────────
    # Ensure the "ovrm_id" custom field exists on bulletins. Idempotent.
    ovrm_field = DynamicField.query.filter_by(name="ovrm_id", entity_type="bulletin").first()
    if not ovrm_field:
        ovrm_field = DynamicField(
            name="ovrm_id",
            title="OVRM ID",
            entity_type="bulletin",
            field_type=DynamicField.TEXT,
            ui_component=DynamicField.UIComponent.INPUT,
            schema_config={"max_length": 50},
            ui_config={"width": "w-50", "help_text": "Ouse Valley Rights Monitor internal reference number"},
            searchable=True,
            sort_order=20,
            core=False,
            active=True,
        )
        db.session.add(ovrm_field)
        db.session.flush()
        ovrm_field.create_column()
        db.session.commit()
        print("  Created OVRM ID custom field on bulletin")
    else:
        print("  OVRM ID custom field already exists")

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
        ("user1", "Analyst One",   "analyst1@ovrm.local"),
        ("user2", "Analyst Two",   "analyst2@ovrm.local"),
        ("user3", "Analyst Three", "analyst3@ovrm.local"),
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
    wf_human_created = WorkflowStatus.query.filter_by(title="Human Created").first()
    status = wf_human_created.title if wf_human_created else "Human Created"
    status_assigned = status  # All sample data uses Human Created status (manually uploaded)
    evt_types = {et.title: et for et in Eventtype.query.all()}
    pv = {v.title: v for v in PotentialViolation.query.all()}
    cv = {v.title: v for v in ClaimedViolation.query.all()}

    from geoalchemy2.shape import from_shape
    from shapely.geometry import Point

    # ── Sources ─────────────────────────────────────────────────────
    source_titles = [
        "X (Twitter)",
        "Albion Broadcasting",
        "Lewes & Weald Constabulary",
        "The National Courier",
        "ITV News",
        "Sky News",
        "Instagram",
        "Facebook",
        "YouTube",
        "Witness Statement",
        "TikTok",
        "Lewes Clarion Newspaper",
        "The Argus",
        "Sussex Police",
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
    lewes.latlng = from_shape(Point(-0.0030, 50.8762), srid=4326)
    db.session.add(lewes)
    db.session.flush()

    castle = Location(
        title="Lewes Castle",
        location_type_id=loc_type_poi.id if loc_type_poi else None,
        country_id=uk.id if uk else None,
        parent_id=lewes.id,
    )
    castle.latlng = from_shape(Point(0.0074, 50.8729), srid=4326)
    db.session.add(castle)
    db.session.flush()

    crown_court = Location(
        title="Lewes Crown Court",
        location_type_id=loc_type_poi.id if loc_type_poi else None,
        country_id=uk.id if uk else None,
        parent_id=lewes.id,
    )
    crown_court.latlng = from_shape(Point(0.0102, 50.8721), srid=4326)
    db.session.add(crown_court)
    db.session.flush()

    police_station = Location(
        title="Lewes Police Station",
        location_type_id=loc_type_poi.id if loc_type_poi else None,
        country_id=uk.id if uk else None,
        parent_id=lewes.id,
    )
    police_station.latlng = from_shape(Point(0.01148, 50.8751), srid=4326)
    db.session.add(police_station)
    db.session.flush()

    lewes_prison = Location(
        title="HM Prison Lewes",
        location_type_id=loc_type_poi.id if loc_type_poi else None,
        country_id=uk.id if uk else None,
        parent_id=lewes.id,
    )
    lewes_prison.latlng = from_shape(Point(-0.0133, 50.8732), srid=4326)
    db.session.add(lewes_prison)
    db.session.flush()

    brighton = Location(
        title="Brighton",
        location_type_id=loc_type_admin.id if loc_type_admin else None,
        admin_level_id=admin_level.get("Town").id if admin_level.get("Town") else None,
        country_id=uk.id if uk else None,
        parent_id=east_sussex.id,
    )
    brighton.latlng = from_shape(Point(-0.1372, 50.8225), srid=4326)
    db.session.add(brighton)
    db.session.flush()

    eastbourne = Location(
        title="Eastbourne",
        location_type_id=loc_type_admin.id if loc_type_admin else None,
        admin_level_id=admin_level.get("Town").id if admin_level.get("Town") else None,
        country_id=uk.id if uk else None,
        parent_id=east_sussex.id,
    )
    eastbourne.latlng = from_shape(Point(0.2797, 50.7684), srid=4326)
    db.session.add(eastbourne)
    db.session.flush()

    hastings = Location(
        title="Hastings",
        location_type_id=loc_type_admin.id if loc_type_admin else None,
        admin_level_id=admin_level.get("Town").id if admin_level.get("Town") else None,
        country_id=uk.id if uk else None,
        parent_id=east_sussex.id,
    )
    hastings.latlng = from_shape(Point(0.5730, 50.8543), srid=4326)
    db.session.add(hastings)
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

    crown_court.full_location = "Lewes Crown Court, Lewes, East Sussex"
    crown_court.id_tree = f"[{crown_court.id}] [{lewes.id}] [{east_sussex.id}]"

    police_station.full_location = "Lewes Police Station, Lewes, East Sussex"
    police_station.id_tree = f"[{police_station.id}] [{lewes.id}] [{east_sussex.id}]"

    lewes_prison.full_location = "HM Prison Lewes, Lewes, East Sussex"
    lewes_prison.id_tree = f"[{lewes_prison.id}] [{lewes.id}] [{east_sussex.id}]"

    brighton.full_location = "Brighton, East Sussex"
    brighton.id_tree = f"[{brighton.id}] [{east_sussex.id}]"

    brighton_dome = Location(
        title="Brighton Dome",
        location_type_id=loc_type_poi.id if loc_type_poi else None,
        country_id=uk.id if uk else None,
        parent_id=brighton.id,
    )
    brighton_dome.latlng = from_shape(Point(-0.1390, 50.8237), srid=4326)
    db.session.add(brighton_dome)
    db.session.flush()
    brighton_dome.full_location = "Brighton Dome, Brighton, East Sussex"
    brighton_dome.id_tree = f"[{brighton_dome.id}] [{brighton.id}] [{east_sussex.id}]"

    eastbourne.full_location = "Eastbourne, East Sussex"
    eastbourne.id_tree = f"[{eastbourne.id}] [{east_sussex.id}]"

    hastings.full_location = "Hastings, East Sussex"
    hastings.id_tree = f"[{hastings.id}] [{east_sussex.id}]"

    meridian_house = Location(
        title="Meridian House, Harvey's Brewery Site",
        location_type_id=loc_type_poi.id if loc_type_poi else None,
        country_id=uk.id if uk else None,
        parent_id=lewes.id,
    )
    meridian_house.latlng = from_shape(Point(0.01664, 50.87484), srid=4326)
    db.session.add(meridian_house)
    db.session.flush()
    meridian_house.full_location = "Meridian House, Harvey's Brewery Site, Lewes, East Sussex"
    meridian_house.id_tree = f"[{meridian_house.id}] [{lewes.id}] [{east_sussex.id}]"

    db.session.flush()

    # ── Labels ─────────────────────────────────────────────────────────
    # Investigation labels: hierarchical tree for organising content by case.
    #
    label_map = {}

    # ── Investigation labels (hierarchical) ──────────────────────────
    # Parent
    inv_parent = Label(title="Investigations", order=1, verified=False,
                       for_bulletin=True, for_actor=True, for_incident=True)
    db.session.add(inv_parent)
    db.session.flush()
    label_map["Investigations"] = inv_parent

    # Children of Investigations
    inv_lewes = Label(title="Lewes Castle Siege", order=2, verified=False,
                      parent_label_id=inv_parent.id,
                      for_bulletin=True, for_actor=True, for_incident=True)
    inv_brighton = Label(title="Brighton Dome Rally", order=3, verified=False,
                         parent_label_id=inv_parent.id,
                         for_bulletin=True, for_actor=True, for_incident=True)
    db.session.add(inv_lewes)
    db.session.add(inv_brighton)
    db.session.flush()
    label_map["Lewes Castle Siege"] = inv_lewes
    label_map["Brighton Dome Rally"] = inv_brighton


    # ── Actor ───────────────────────────────────────────────────────
    a = Actor()
    a.name = "Thomas Ashdown"
    a.first_name = "Thomas"
    a.middle_name = "James"
    a.last_name = "Ashdown"
    a.nickname = "Tom"
    a.father_name = "Robert"
    a.mother_name = "Patricia"
    a.sex = "Male"
    a.age = "Adult"
    a.civilian = "Civilian"
    a.type = "Person"
    a.occupation = "Self-employed builder"
    a.position = "Organiser, Lewes Heritage Trust"
    a.family_status = "Married"
    a.no_children = 2
    a.comments = (
        "Identified in social media imagery at the front of the crowd "
        "outside Lewes Castle on 17 March 2026. Seen carrying a placard "
        "and shouting through a megaphone. Lewes resident, self-employed "
        "builder. Named by The National Courier as 'one of the organisers' of the "
        "Lewes Heritage Trust occupation. Arrested on 19 March 2026 during "
        "the clearance operation; charged with violent disorder and aggravated "
        "trespass. His legal representative declined to comment."
    )
    a.status = status
    a.assigned_to_id = test_users["user2"].id  # Actor ID 1: assigned
    a.first_peer_reviewer_id = test_users["user3"].id
    a.second_peer_reviewer_id = test_users["user1"].id
    a.tags = []
    a.id_number = [
        {"type": "7", "number": "CRN/2026/LEW/00312"},
        {"type": "4", "number": "T20261234"},
    ]
    db.session.add(a)
    db.session.flush()

    uk = Country.query.filter_by(title="United Kingdom").first()
    if uk:
        a.nationalities.append(uk)

    a.origin_place_id = lewes.id

    profile = ActorProfile(actor_id=a.id, mode=2)
    profile.originid = "x-lewes-castle-17mar2026-ashdown"
    profile.description = (
        "Thomas James Ashdown (b. approx. 1984), self-employed builder and "
        "resident of Lewes, East Sussex. First identified on 17 March 2026 in "
        "an X (Twitter) post showing him at the front of the crowd outside "
        "Lewes Castle, carrying a placard and using a megaphone. Subsequently "
        "named by The National Courier (19 March 2026) as 'one of the organisers' of "
        "the Lewes Heritage Trust occupation of the castle. Eyewitness Margaret "
        "Okafor confirmed (18 March statement) that a man matching his description "
        "was near the front of the crowd when the barbican gate was breached. "
        "Arrested on 19 March 2026 during the clearance operation. Charged with "
        "violent disorder (Public Order Act 1986, s.2) and aggravated trespass "
        "(Criminal Justice and Public Order Act 1994, s.68). His legal "
        "representative declined to comment."
    )
    profile.source_link = "https://x.com/lewes_local/status/1901234567890"
    profile.publish_date = _dt(2026, 3, 17, 14, 22)
    profile.documentation_date = _dt(2026, 3, 19, 20, 0)
    profile.sources.append(sources["X (Twitter)"])
    profile.sources.append(sources["The National Courier"])
    profile.labels.append(label_map["Lewes Castle Siege"])
    db.session.add(profile)

    # ── Actor events ────────────────────────────────────────────────
    evt_arrested_type = Eventtype.query.filter_by(title="Arrested").first()
    evt_charged_type = Eventtype.query.filter_by(title="Charged").first()

    actor_evt_arrested = Event(
        title="Thomas Ashdown arrested during castle clearance",
        eventtype_id=evt_arrested_type.id if evt_arrested_type else None,
        from_date=_dt(2026, 3, 19, 7, 30),
        to_date=_dt(2026, 3, 19, 8, 0),
        location_id=castle.id,
    )
    db.session.add(actor_evt_arrested)
    db.session.flush()
    a.events.append(actor_evt_arrested)

    actor_evt_charged = Event(
        title="Charged with violent disorder and aggravated trespass",
        eventtype_id=evt_charged_type.id if evt_charged_type else None,
        from_date=_dt(2026, 3, 19, 15, 30),
        to_date=_dt(2026, 3, 19, 15, 30),
        location_id=police_station.id,
    )
    db.session.add(actor_evt_charged)
    db.session.flush()
    a.events.append(actor_evt_charged)

    # ── Actor 2: Rachel Pemberton ────────────────────────────────────
    a2 = Actor()
    a2.name = "Rachel Pemberton"
    a2.first_name = "Rachel"
    a2.middle_name = "Anne"
    a2.last_name = "Pemberton"
    a2.sex = "Female"
    a2.age = "Adult"
    a2.civilian = "Civilian"
    a2.type = "Person"
    a2.occupation = "Retired secondary school teacher"
    a2.position = "Chair, Lewes Heritage Trust"
    a2.family_status = "Widowed"
    a2.no_children = 1
    a2.comments = (
        "Chair of the Lewes Heritage Trust. Arrested on 19 March 2026 during "
        "the clearance of Lewes Castle alongside Thomas Ashdown. Named by The "
        "National Courier as 'a leader of the occupation'. Long-standing Lewes "
        "resident and retired history teacher; well known locally as a heritage "
        "campaigner. Released on bail. No charges confirmed at time of writing."
    )
    a2.status = status
    a2.assigned_to_id = test_users["user1"].id  # Actor ID 2: assigned
    a2.first_peer_reviewer_id = test_users["user2"].id
    a2.second_peer_reviewer_id = test_users["user3"].id
    a2.tags = []
    a2.id_number = [{"type": "7", "number": "CRN/2026/LEW/00313"}]
    db.session.add(a2)
    db.session.flush()

    uk2 = Country.query.filter_by(title="United Kingdom").first()
    if uk2:
        a2.nationalities.append(uk2)
    a2.origin_place_id = lewes.id

    profile2 = ActorProfile(actor_id=a2.id, mode=2)
    profile2.originid = "nationalcourier-lewes-castle-19mar2026-pemberton"
    profile2.description = (
        "Rachel Anne Pemberton (b. approx. 1961), retired secondary school "
        "history teacher and Chair of the Lewes Heritage Trust. Long-standing "
        "resident of Lewes and prominent local heritage campaigner. Arrested on "
        "19 March 2026 during the clearance of Lewes Castle; named by The "
        "National Courier alongside Thomas Ashdown as 'a leader of the "
        "occupation'. Released on bail the same evening. No charges confirmed "
        "at the time of documentation. Her role as Chair of the Trust makes her "
        "the senior figure of the two named organisers; Ashdown is understood "
        "to have handled operational planning."
    )
    profile2.source_link = "https://www.thenationalcourier.co.uk/uk-news/2026/mar/19/lewes-castle-siege-ends"
    profile2.publish_date = _dt(2026, 3, 19, 14, 20)
    profile2.documentation_date = _dt(2026, 3, 23, 9, 0)
    profile2.sources.append(sources["The National Courier"])
    profile2.sources.append(sources["Witness Statement"])
    profile2.labels.append(label_map["Lewes Castle Siege"])
    db.session.add(profile2)

    a2_evt_arrested = Event(
        title="Rachel Pemberton arrested during castle clearance",
        eventtype_id=evt_arrested_type.id if evt_arrested_type else None,
        from_date=_dt(2026, 3, 19, 7, 30),
        to_date=_dt(2026, 3, 19, 8, 0),
        location_id=castle.id,
    )
    db.session.add(a2_evt_arrested)
    db.session.flush()
    a2.events.append(a2_evt_arrested)

    evt_released_type = Eventtype.query.filter_by(title="Released").first()
    a2_evt_released = Event(
        title="Rachel Pemberton released on bail",
        eventtype_id=evt_released_type.id if evt_released_type else None,
        from_date=_dt(2026, 3, 19, 18, 30),
        to_date=_dt(2026, 3, 19, 18, 30),
        location_id=police_station.id,
    )
    db.session.add(a2_evt_released)
    db.session.flush()
    a2.events.append(a2_evt_released)

    # ── Actor 3: Kieran Moss ─────────────────────────────────────────
    a3 = Actor()
    a3.name = "Kieran Moss"
    a3.first_name = "Kieran"
    a3.last_name = "Moss"
    a3.sex = "Male"
    a3.age = "Adult"
    a3.civilian = "Civilian"
    a3.type = "Person"
    a3.occupation = "Postgraduate student, Southdown University"
    a3.position = "Volunteer, Lewes Heritage Trust"
    a3.family_status = "Single"
    a3.comments = (
        "Identified in the X post from the Phoenix Causeway Tesco car park "
        "protest on 18 March 2026 (Bulletin 11). Believed to have led the "
        "secondary protest group. Not arrested. His knowledge of the Lewes "
        "Heritage Trust campaign and proximity to the Meridian House site area "
        "has been noted in connection with Incident 3, but there is no evidence "
        "linking him to the criminal damage. Documentation ongoing."
    )
    a3.status = status_assigned
    a3.assigned_to_id = test_users["user2"].id  # Actor ID 3: assigned
    a3.first_peer_reviewer_id = test_users["user1"].id
    a3.tags = []
    a3.id_number = []
    db.session.add(a3)
    db.session.flush()

    uk3 = Country.query.filter_by(title="United Kingdom").first()
    if uk3:
        a3.nationalities.append(uk3)
    a3.origin_place_id = brighton.id

    profile3 = ActorProfile(actor_id=a3.id, mode=2)
    profile3.originid = "x-phoenix-causeway-18mar2026-moss"
    profile3.description = (
        "Kieran Moss, postgraduate student believed to be based in Brighton. "
        "Identified from an X post (18 March 2026, 13:04 GMT) showing him at "
        "the front of the protest group at the Tesco superstore car park, "
        "Phoenix Causeway, Lewes. Believed to have coordinated the secondary "
        "protest on day 2 of the castle occupation. Not arrested. Confirmed as "
        "a volunteer with Lewes Heritage Trust via cross-referencing his social "
        "media profile with the Trust's public communications. No criminal record "
        "identified. Flagged as a person of interest in connection with Incident 3 "
        "(criminal damage, Meridian House site) but with no supporting evidence."
    )
    profile3.source_link = "https://x.com/lewes_watch/status/1901234999001"
    profile3.publish_date = _dt(2026, 3, 18, 13, 4)
    profile3.documentation_date = _dt(2026, 3, 24, 14, 0)
    profile3.sources.append(sources["X (Twitter)"])
    profile3.labels.append(label_map["Lewes Castle Siege"])
    db.session.add(profile3)

    # ── Event type lookups (used throughout bulletin/incident creation)
    et_pre = evt_types.get("Pre-Incident")
    et = evt_types.get("Incident")
    et_post = evt_types.get("Post-Incident")
    et_pub = evt_types.get("Publication")

    # ── Pre-incident: Lewes Clarion Newspaper article ────────────────────────
    b_pre = Bulletin()
    b_pre.title = (
        "Anger in Lewes as council approves demolition of Meridian House"
    )
    b_pre.sjac_title = "Lewes Clarion Newspaper: council approves demolition of Meridian House — 3 Mar 2026"
    b_pre.description = (
        "Lewes Clarion Newspaper article published online at 09:15 GMT on 3 March 2026. "
        "Reports that Lewes District Council voted 7–4 to approve a planning "
        "application for the demolition of Meridian House, a Grade II listed "
        "Victorian building adjacent to Lewes Castle, to make way for a mixed-use "
        "development. The decision was met with protests from residents inside and "
        "outside the public gallery. Heritage campaign group 'Lewes Heritage Trust' "
        "issued a statement describing the decision as 'a betrayal of Lewes's "
        "identity' and warning that 'direct action will follow if this decision "
        "is not reversed'. "
        "\n\n"
        "The article quotes councillor Diana Forsythe (Conservative) defending the "
        "decision on economic grounds, and local historian Dr. Caroline Voss calling "
        "it 'an irreversible loss to one of England's best-preserved medieval towns'. "
        "A petition against the demolition has received 4,200 signatures."
    )
    b_pre.originid = "lc-meridian-house-03mar2026"
    b_pre.source_link = "https://www.lewesclarion.co.uk/news/lewes/meridian-house-demolition-approved-2026"
    b_pre.publish_date = _dt(2026, 3, 3, 9, 15)
    b_pre.documentation_date = _dt(2026, 3, 19, 17, 0)
    b_pre.reliability_score = 70
    b_pre.comments = (
        "Documented retrospectively on 19 March once the connection to the siege "
        "was established. The National Courier article of 19 March names 'Lewes Heritage Trust' "
        "and cites the Meridian House demolition as the trigger for the occupation. "
        "This article establishes the group's stated intent to take direct action "
        "and names Dr. Caroline Voss — who later issued the damage statement — as "
        "an opponent of the demolition. Key context for the incident."
    )
    b_pre.status = status_assigned
    b_pre.user_id = admin.id
    b_pre.assigned_to_id = test_users["user1"].id  # Bulletin ID 1: assigned
    b_pre.tags = []
    db.session.add(b_pre)
    db.session.flush()

    b_pre.labels.append(label_map["Lewes Castle Siege"])
    b_pre.locations.append(lewes)
    b_pre.sources.append(sources["Lewes Clarion Newspaper"])

    geo_type_comm = GeoLocationType.query.filter_by(title="Commercial/Retail").first()
    geo_meridian = GeoLocation()
    geo_meridian.title = "Meridian House (proposed demolition site)"
    geo_meridian.latlng = "POINT(0.01664 50.87484)"
    geo_meridian.type_id = geo_type_comm.id if geo_type_comm else None
    geo_meridian.main = False
    geo_meridian.comment = "Grade II listed Victorian building at the Harvey's Brewery site. Subject of the planning application that triggered the protest."
    geo_meridian.bulletin_id = b_pre.id
    db.session.add(geo_meridian)
    db.session.flush()

    pre_evt = Event(
        title="Lewes District Council votes to approve demolition of Meridian House",
        eventtype_id=et_pre.id if et_pre else None,  # Pre-Incident
        from_date=_dt(2026, 3, 3, 18, 0),
        to_date=_dt(2026, 3, 3, 21, 0),
        location_id=meridian_house.id,
        comments="Council vote triggers Lewes Heritage Trust warning of direct action.",
    )
    db.session.add(pre_evt)
    db.session.flush()
    b_pre.events.append(pre_evt)

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
    b.assigned_to_id = user1.id  # Bulletin ID 2: assigned
    b.tags = []
    db.session.add(b)
    db.session.flush()

    b.labels.append(label_map["Lewes Castle Siege"])

    b.locations.append(castle)
    b.sources.append(src)

    # ── GeoLocation (map marker) ──────────────────────────────────
    geo_type_hist = GeoLocationType.query.filter_by(title="Historic Monument").first()

    geo = GeoLocation()
    geo.title = "Lewes Castle"
    geo.latlng = "POINT(0.0074 50.8729)"
    geo.type_id = geo_type_hist.id if geo_type_hist else None
    geo.main = True
    geo.comment = "11th-century Norman castle. Crowd gathered at the barbican gate."
    geo.bulletin_id = b.id
    db.session.add(geo)

    db.session.flush()

    # ── Bulletin event ──────────────────────────────────────────────

    evt = Event(
        title="Crowd forces entry through barbican gate",
        eventtype_id=et.id if et else None,  # Incident
        from_date=_dt(2026, 3, 17, 14, 0),
        to_date=_dt(2026, 3, 17, 14, 30),
        location_id=castle.id,
    )
    db.session.add(evt)
    db.session.flush()
    b.events.append(evt)

    evt_pub_b = Event(
        title="X post published by @lewes_local",
        eventtype_id=et_pub.id if et_pub else None,  # Publication
        from_date=_dt(2026, 3, 17, 14, 22),
        to_date=_dt(2026, 3, 17, 14, 22),
        location_id=castle.id,
    )
    db.session.add(evt_pub_b)
    db.session.flush()
    b.events.append(evt_pub_b)

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
    b_fb.assigned_to_id = test_users["user2"].id  # Bulletin ID 3: assigned
    b_fb.tags = []
    db.session.add(b_fb)
    db.session.flush()

    b_fb.labels.append(label_map["Lewes Castle Siege"])
    b_fb.locations.append(castle)
    b_fb.sources.append(sources["Facebook"])
    b_fb.events.append(evt)

    # ── GeoLocation (map marker) ──────────────────────────────────
    geo_type_infra = GeoLocationType.query.filter_by(title="Infrastructure").first()

    geo_fb = GeoLocation()
    geo_fb.title = "Approach road south of Lewes Castle"
    geo_fb.latlng = "POINT(0.0068 50.8718)"
    geo_fb.type_id = geo_type_infra.id if geo_type_infra else None
    geo_fb.main = False
    geo_fb.comment = "Road south of the castle barbican — location of police vehicles and crowd photographed from car window."
    geo_fb.bulletin_id = b_fb.id
    db.session.add(geo_fb)
    db.session.flush()

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
    b_ig.assigned_to_id = test_users["user3"].id  # Bulletin ID 4: assigned
    b_ig.tags = []
    db.session.add(b_ig)
    db.session.flush()

    b_ig.labels.append(label_map["Lewes Castle Siege"])
    b_ig.locations.append(castle)
    b_ig.sources.append(sources["Instagram"])
    b_ig.events.append(evt)

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
    b_tt.assigned_to_id = test_users["user1"].id  # Bulletin ID 5: assigned
    b_tt.tags = []
    db.session.add(b_tt)
    db.session.flush()

    b_tt.labels.append(label_map["Lewes Castle Siege"])
    b_tt.locations.append(castle)
    b_tt.sources.append(sources["TikTok"])
    b_tt.events.append(evt)

    # ── Eyewitness statement bulletin ──────────────────────────────
    b_ew = Bulletin()
    b_ew.title = (
        "Witness statement — Margaret Okafor, 17 March 2026. "
        "I was working in the castle ticket office when the crowd arrived."
    )
    b_ew.sjac_title = "Witness statement: castle ticket office staff member — 17 Mar 2026"
    b_ew.description = (
        "Written statement provided by Margaret Okafor, ticket office supervisor "
        "at Lewes Castle, taken by Lewes & Weald Constabulary on 18 March 2026 (ref: SP-2026-0317-04). "
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
        "with 11 years at the castle. Statement taken under caution by Lewes & Weald Constabulary "
        "the day after the incident. Key value: confirms the gate breach mechanism, "
        "the presence of a school group, the timing of the keep damage, and places a "
        "person matching Ashdown's description at the front of the crowd. "
        "No corroboration needed — consistent with all other evidence."
    )
    b_ew.status = status_assigned
    b_ew.user_id = admin.id
    # b_ew.assigned_to_id not set (bulletin ID 6: unassigned)
    b_ew.tags = []
    db.session.add(b_ew)
    db.session.flush()

    b_ew.labels.append(label_map["Lewes Castle Siege"])
    b_ew.locations.append(castle)
    b_ew.sources.append(sources["Witness Statement"])

    ew_evt = Event(
        title="Witness statement taken by Lewes & Weald Constabulary",
        eventtype_id=et_post.id if et_post else None,  # Post-Incident
        from_date=_dt(2026, 3, 18, 10, 30),
        to_date=_dt(2026, 3, 18, 10, 30),
        location_id=castle.id,
        comments="Statement by Margaret Okafor, ticket office supervisor, reference SP-2026-0317-04.",
    )
    db.session.add(ew_evt)
    db.session.flush()
    b_ew.events.append(ew_evt)

    # ── Day 2: Albion Broadcasting article ─────────────────────────────────────
    b_bbc = Bulletin()
    b_bbc.title = (
        "Lewes Castle siege enters second night as police establish cordon"
    )
    b_bbc.sjac_title = "Albion Broadcasting article: day 2 of Lewes Castle occupation — 18 Mar 2026"
    b_bbc.description = (
        "Albion Broadcasting online article published at 17:45 GMT on 18 March 2026. "
        "Reports that approximately 80 protesters remain inside the castle grounds "
        "following an overnight occupation. Lewes & Weald Constabulary have established a cordon "
        "around the perimeter and declared the surrounding streets a Section 14 area "
        "under the Public Order Act. A police spokesperson confirmed that formal "
        "negotiations with protest organisers began at 09:00. Site curator Dr. Caroline Voss "
        "issued a statement via the National Monuments Authority describing 'significant damage "
        "to the east wall of the Norman keep' and calling for the immediate evacuation "
        "of the site. No injuries reported. The article includes aerial photography "
        "sourced from a commercial drone operator showing tents pitched in the outer ward."
    )
    b_bbc.originid = "albion-lewes-castle-18mar2026"
    b_bbc.source_link = "https://www.albionbroadcasting.co.uk/news/uk-england-sussex-lewes-castle-18mar2026"
    b_bbc.publish_date = _dt(2026, 3, 18, 17, 45)
    b_bbc.documentation_date = _dt(2026, 3, 18, 20, 0)
    b_bbc.reliability_score = 75
    b_bbc.comments = (
        "Credible national news source. Article cites named police spokesperson and "
        "Dr. Caroline Voss directly — both independently corroborated. Aerial photograph "
        "confirms continued occupation and scale. Crowd figure of 80 is lower than day 1 "
        "estimate of 200 — consistent with overnight attrition."
    )
    b_bbc.status = status_assigned
    b_bbc.user_id = admin.id
    # b_bbc.assigned_to_id not set (bulletin ID 7: unassigned)
    b_bbc.tags = []
    db.session.add(b_bbc)
    db.session.flush()

    b_bbc.labels.append(label_map["Lewes Castle Siege"])
    b_bbc.locations.append(castle)
    b_bbc.sources.append(sources["Albion Broadcasting"])

    # ── Day 2: Lewes & Weald Constabulary press statement ────────────────────────
    b_sp = Bulletin()
    b_sp.title = (
        "Lewes & Weald Constabulary: statement regarding Lewes Castle major incident — 18 March 2026"
    )
    b_sp.sjac_title = "Lewes & Weald Constabulary press statement: day 2 update — 18 Mar 2026"
    b_sp.description = (
        "Official press statement published by Lewes & Weald Constabulary at 12:00 GMT on "
        "18 March 2026 (reference: SP-PRESS-2026-0318-01). "
        "\n\n"
        "\"Lewes & Weald Constabulary can confirm that a major incident declared at Lewes Castle "
        "on 17 March 2026 remains ongoing. Approximately 80 individuals are currently "
        "occupying the castle grounds. A cordon has been established and negotiations "
        "are underway. We are working to resolve this situation peacefully. "
        "\n\n"
        "A Section 14 direction has been issued for the surrounding area under the "
        "Public Order Act 1986. Members of the public are asked to avoid the town "
        "centre. No serious injuries have been reported. Anyone with information is "
        "asked to contact Lewes & Weald Constabulary on 101 quoting reference 2026-0317.\""
    )
    b_sp.originid = "SP-PRESS-2026-0318-01"
    b_sp.source_link = "https://www.leweswealdconstabulary.police.uk/news/lewes-castle-major-incident-day2"
    b_sp.publish_date = _dt(2026, 3, 18, 12, 0)
    b_sp.documentation_date = _dt(2026, 3, 18, 15, 30)
    b_sp.reliability_score = 85
    b_sp.comments = (
        "Official police statement — high reliability for factual claims about police "
        "actions (cordon, Section 14, negotiations). Crowd figure of ~80 consistent "
        "with BBC report. Statement is cautiously worded — does not confirm damage "
        "or name individuals."
    )
    b_sp.status = status_assigned
    b_sp.user_id = admin.id
    # b_sp.assigned_to_id not set (bulletin ID 8: unassigned)
    b_sp.tags = []
    db.session.add(b_sp)
    db.session.flush()

    b_sp.labels.append(label_map["Lewes Castle Siege"])
    b_sp.locations.append(castle)
    b_sp.sources.append(sources["Lewes & Weald Constabulary"])

    # ── Day 3: The National Courier article ─────────────────────────────────
    b_grdn = Bulletin()
    b_grdn.title = (
        "Lewes Castle protesters disperse after three-day occupation — seven arrested"
    )
    b_grdn.sjac_title = "The National Courier article: end of Lewes Castle siege — 19 Mar 2026"
    b_grdn.description = (
        "The National Courier online article published at 14:20 GMT on 19 March 2026. "
        "Reports that the three-day occupation of Lewes Castle ended at approximately "
        "11:00 GMT after protesters agreed to leave voluntarily following overnight "
        "negotiations. Seven individuals were arrested on suspicion of aggravated "
        "trespass and criminal damage under the Criminal Justice and Public Order "
        "Act 1994. The article names the protest group as 'Lewes Heritage Trust' and "
        "states their demands related to the proposed demolition of a nearby listed "
        "building. National Monuments Authority confirmed the castle would remain closed for "
        "structural assessment. The article quotes Thomas Ashdown by name as 'one "
        "of the organisers' — his legal representative declined to comment."
    )
    b_grdn.originid = "nationalcourier-lewes-castle-19mar2026"
    b_grdn.source_link = "https://www.thenationalcourier.co.uk/uk-news/2026/mar/19/lewes-castle-siege-ends"
    b_grdn.publish_date = _dt(2026, 3, 19, 14, 20)
    b_grdn.documentation_date = _dt(2026, 3, 19, 16, 0)
    b_grdn.reliability_score = 75
    b_grdn.comments = (
        "Names Ashdown as an organiser — first source to do so explicitly. "
        "Seven arrests figure consistent with police statement. Protest group name "
        "'Lewes Heritage Trust' not corroborated elsewhere yet — treat as unverified. "
        "Castle closure confirmed independently via National Monuments Authority website."
    )
    b_grdn.status = status_assigned
    b_grdn.user_id = admin.id
    # b_grdn.assigned_to_id not set (bulletin ID 9: unassigned)
    b_grdn.tags = []
    db.session.add(b_grdn)
    db.session.flush()

    b_grdn.labels.append(label_map["Lewes Castle Siege"])
    b_grdn.locations.append(castle)
    b_grdn.sources.append(sources["The National Courier"])

    # ── Day 3: Lewes & Weald Constabulary arrest statement ───────────────────────
    b_sp2 = Bulletin()
    b_sp2.title = (
        "Lewes & Weald Constabulary: seven arrests following Lewes Castle occupation — 19 March 2026"
    )
    b_sp2.sjac_title = "Lewes & Weald Constabulary press statement: arrests and closure — 19 Mar 2026"
    b_sp2.description = (
        "Official press statement published by Lewes & Weald Constabulary at 13:30 GMT on "
        "19 March 2026 (reference: SP-PRESS-2026-0319-01). "
        "\n\n"
        "\"Lewes & Weald Constabulary can confirm that the major incident at Lewes Castle has now "
        "concluded. The site was cleared of all unauthorised persons at approximately "
        "11:00 GMT on 19 March 2026. Seven individuals, aged between 22 and 47, "
        "have been arrested on suspicion of aggravated trespass and criminal damage. "
        "All are currently in custody. "
        "\n\n"
        "We would like to thank the public for their patience during this incident. "
        "The castle remains closed pending a structural survey by National Monuments Authority. "
        "An investigation into the circumstances of the occupation is ongoing.\""
    )
    b_sp2.originid = "SP-PRESS-2026-0319-01"
    b_sp2.source_link = "https://www.leweswealdconstabulary.police.uk/news/lewes-castle-major-incident-resolved"
    b_sp2.publish_date = _dt(2026, 3, 19, 13, 30)
    b_sp2.documentation_date = _dt(2026, 3, 19, 15, 0)
    b_sp2.reliability_score = 90
    b_sp2.comments = (
        "High reliability — official police statement confirming end of incident, "
        "arrest count (7), age range, and charges. Confirms castle closure. "
        "Does not name individuals arrested."
    )
    b_sp2.status = status_assigned
    b_sp2.user_id = admin.id
    # b_sp2.assigned_to_id not set (bulletin ID 10: unassigned)
    b_sp2.tags = []
    db.session.add(b_sp2)
    db.session.flush()

    b_sp2.labels.append(label_map["Lewes Castle Siege"])
    b_sp2.locations.append(castle)
    b_sp2.sources.append(sources["Lewes & Weald Constabulary"])

    # ── Actor-to-Bulletin links ─────────────────────────────────────
    # X post: Ashdown visible at front of crowd (Appeared, Certain)
    atob = Atob(actor_id=a.id, bulletin_id=b.id)
    atob.related_as = [4]  # Appeared
    atob.probability = 2  # Certain
    atob.comment = "Ashdown visible at the front of the crowd in the X post image."
    atob.user_id = admin.id
    db.session.add(atob)

    # TikTok: interior footage — man matching description, unconfirmed (Appeared, Probable)
    atob_tt = Atob(actor_id=a.id, bulletin_id=b_tt.id)
    atob_tt.related_as = [4]  # Appeared
    atob_tt.probability = 1  # Probable
    atob_tt.comment = "Interior footage shows a man matching Ashdown's description near the keep. Not confirmed."
    atob_tt.user_id = admin.id
    db.session.add(atob_tt)

    # Eyewitness statement: Margaret Okafor confirms man matching his description (Subject, Certain)
    atob_ew = Atob(actor_id=a.id, bulletin_id=b_ew.id)
    atob_ew.related_as = [6]  # Subject
    atob_ew.probability = 2  # Certain
    atob_ew.comment = "Okafor confirmed man matching Ashdown's description near barbican gate when breached."
    atob_ew.user_id = admin.id
    db.session.add(atob_ew)

    # Guardian: names Ashdown as organiser (Appeared, Certain)
    atob_grdn = Atob(actor_id=a.id, bulletin_id=b_grdn.id)
    atob_grdn.related_as = [4]  # Appeared
    atob_grdn.probability = 2  # Certain
    atob_grdn.comment = "Guardian article names Ashdown by name as 'one of the organisers'."
    atob_grdn.user_id = admin.id
    db.session.add(atob_grdn)

    # Rachel Pemberton: National Courier (Appeared, Certain) + X post (Appeared, Probable)
    atob_p1 = Atob(actor_id=a2.id, bulletin_id=b_grdn.id)
    atob_p1.related_as = [4]  # Appeared
    atob_p1.probability = 2  # Certain
    atob_p1.comment = "National Courier names Pemberton as 'a leader of the occupation'."
    atob_p1.user_id = admin.id
    db.session.add(atob_p1)

    atob_p2 = Atob(actor_id=a2.id, bulletin_id=b.id)
    atob_p2.related_as = [4]  # Appeared
    atob_p2.probability = 1  # Probable
    atob_p2.comment = "Pemberton likely in crowd but not individually identified in X post image."
    atob_p2.user_id = admin.id
    db.session.add(atob_p2)

    db.session.flush()

    # ── Incident ────────────────────────────────────────────────────
    inc = Incident()
    inc.title = "Unlawful occupation and criminal damage — Lewes Castle, 17–19 March 2026"
    inc.description = (
        "On 17 March 2026 a crowd of approximately 200 people converged on "
        "Lewes Castle in the town of Lewes, East Sussex. The group forced entry "
        "through the barbican gate at around 14:00 GMT and occupied the castle "
        "grounds. Police declared a major incident at 14:45. Minor damage was "
        "reported to the 11th-century Norman keep. Protesters remained inside "
        "overnight as police established a cordon around the site. On 18 March "
        "formal negotiations began between police liaison officers and protest "
        "organisers. A statement was issued by site curator Dr. Caroline Voss "
        "confirming structural damage to the keep. On 19 March protesters agreed "
        "to disperse voluntarily; the castle was fully cleared by 11:00 GMT. "
        "Seven arrests were made over the course of the three-day occupation."
    )
    inc.status = status
    inc.assigned_to_id = test_users["user2"].id  # Incident ID 1: assigned
    inc.first_peer_reviewer_id = test_users["user3"].id
    inc.second_peer_reviewer_id = test_users["user1"].id
    inc.comments = (
        "Incident confirmed via cross-referencing the X post image with Albion Broadcasting "
        "and a police press release. Damage to the Norman keep confirmed by "
        "a statement issued by Dr. Caroline Voss, site curator, on 18 March 2026. "
        "Seven arrests confirmed by police press release dated 19 March 2026. "
        "Incident closed and peer reviewed."
    )
    db.session.add(inc)
    db.session.flush()
    inc.labels.append(label_map["Lewes Castle Siege"])

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


    # Incident events
    inc_evt = Event(
        title="Crowd forces entry through barbican gate",
        eventtype_id=et.id if et else None,  # Incident
        from_date=_dt(2026, 3, 17, 14, 0),
        to_date=_dt(2026, 3, 17, 14, 30),
        location_id=castle.id,
    )
    db.session.add(inc_evt)
    db.session.flush()
    inc.events.append(pre_evt)
    inc.events.append(inc_evt)

    inc_evt2 = Event(
        title="Police begin formal negotiations with protest organisers",
        eventtype_id=et_post.id if et_post else None,  # Post-Incident
        from_date=_dt(2026, 3, 18, 9, 0),
        to_date=_dt(2026, 3, 18, 18, 0),
        location_id=castle.id,
        comments=(
            "Police liaison officers established contact with protest leaders. "
            "Dr. Caroline Voss issued a statement confirming damage to the Norman keep."
        ),
    )
    db.session.add(inc_evt2)
    db.session.flush()
    inc.events.append(inc_evt2)
    b_sp.events.append(inc_evt2)

    inc_evt3 = Event(
        title="Castle cleared — protesters disperse, seven arrests made",
        eventtype_id=et_post.id if et_post else None,  # Post-Incident
        from_date=_dt(2026, 3, 19, 7, 0),
        to_date=_dt(2026, 3, 19, 11, 0),
        location_id=castle.id,
        comments=(
            "Protesters agreed to leave voluntarily following overnight negotiations. "
            "Seven individuals arrested on suspicion of aggravated trespass and criminal damage."
        ),
    )
    db.session.add(inc_evt3)
    db.session.flush()
    inc.events.append(inc_evt3)
    b_sp2.events.append(inc_evt3)

    # Publication events for news articles
    pub_evt_bbc = Event(
        title="Albion Broadcasting reports day 2 of Lewes Castle occupation",
        eventtype_id=et_pub.id if et_pub else None,  # Publication
        from_date=_dt(2026, 3, 18, 17, 45),
        to_date=_dt(2026, 3, 18, 17, 45),
        location_id=castle.id,
    )
    db.session.add(pub_evt_bbc)
    db.session.flush()
    b_bbc.events.append(pub_evt_bbc)

    pub_evt_grdn = Event(
        title="The National Courier reports end of siege and seven arrests",
        eventtype_id=et_pub.id if et_pub else None,  # Publication
        from_date=_dt(2026, 3, 19, 14, 20),
        to_date=_dt(2026, 3, 19, 14, 20),
        location_id=castle.id,
    )
    db.session.add(pub_evt_grdn)
    db.session.flush()
    b_grdn.events.append(pub_evt_grdn)

    # Incident-to-Bulletin link
    itob = Itob(incident_id=inc.id, bulletin_id=b.id)
    itob.related_as = 2  # Primary Evidence
    itob.probability = 2  # Certain
    itob.comment = "X post image is the earliest known visual evidence of the crowd."
    itob.user_id = admin.id
    db.session.add(itob)

    # Incident-to-Bulletin link for pre-incident context article
    db.session.add(Itob(
        incident_id=inc.id,
        bulletin_id=b_pre.id,
        related_as=4,  # Context
        probability=2,  # Certain
        comment="Establishes Lewes Heritage Trust's stated intent and the Meridian House demolition as the trigger.",
        user_id=admin.id,
    ))

    # Incident-to-Bulletin links for remaining bulletins
    for new_b, rel_type, prob, comment in [
        (b_fb, 3, 1, "Facebook post corroborates police presence and crowd scale."),
        (b_ig, 3, 1, "Instagram photograph provides best available crowd-size evidence."),
        (b_tt, 2, 2, "TikTok video is only footage from inside the grounds — shows breach and damage."),
        (b_ew, 2, 2, "Eyewitness statement confirms gate breach, keep damage, and Ashdown's position."),
        (b_bbc, 3, 1, "Albion Broadcasting article corroborates day 2 occupation, police cordon, and keep damage."),
        (b_sp, 2, 2, "Official police statement confirms major incident, cordon, and Section 14 direction."),
        (b_grdn, 3, 1, "Guardian article names Ashdown as organiser and reports seven arrests."),
        (b_sp2, 2, 2, "Official police statement confirms end of incident, seven arrests, and castle closure."),
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

    # Incident-to-Actor links for Incident 1
    itoa = Itoa(actor_id=a.id, incident_id=inc.id)
    itoa.related_as = [5]  # Participant
    itoa.probability = 2  # Certain
    itoa.comment = "Ashdown identified as a participant in the siege."
    itoa.user_id = admin.id
    db.session.add(itoa)

    itoa_p = Itoa(actor_id=a2.id, incident_id=inc.id)
    itoa_p.related_as = [5]  # Participant
    itoa_p.probability = 2  # Certain
    itoa_p.comment = "Pemberton named by The National Courier as a leader of the occupation; arrested on site."
    itoa_p.user_id = admin.id
    db.session.add(itoa_p)
    db.session.flush()

    # ── Second incident: Tesco car park protest ──────────────────────
    inc2 = Incident()
    inc2.title = "Unlawful assembly and obstruction — Phoenix Causeway, Lewes, 18 March 2026"
    inc2.description = (
        "On 18 March 2026, during the second day of the Lewes Castle siege, a "
        "secondary group of approximately 60 supporters of the Lewes Heritage Trust "
        "gathered in the car park of the Tesco superstore on Phoenix Causeway, Lewes. "
        "The group blocked access to several loading bays and distributed leaflets "
        "calling for the reversal of the Meridian House demolition decision. "
        "Lewes & Weald Constabulary attended and issued a Section 35 dispersal order under the "
        "Anti-Social Behaviour, Crime and Policing Act 2014. The group dispersed "
        "without arrest by approximately 16:30 GMT."
    )
    inc2.status = status_assigned
    inc2.assigned_to_id = test_users["user1"].id  # Incident ID 2: assigned
    inc2.first_peer_reviewer_id = test_users["user2"].id
    inc2.comments = (
        "Confirmed via X post and Albion Broadcasting coverage. No arrests made. "
        "Likely connected to the castle siege — same protest group, same day."
    )
    db.session.add(inc2)
    db.session.flush()
    inc2.labels.append(label_map["Lewes Castle Siege"])

    for pv_title in ["Public Order Offence", "Trespass"]:
        v = pv.get(pv_title)
        if v:
            inc2.potential_violations.append(v)

    inc2.locations.append(lewes)


    inc2_evt = Event(
        title="Protesters block Tesco loading bays — Section 35 dispersal order issued",
        eventtype_id=et.id if et else None,  # Incident
        from_date=_dt(2026, 3, 18, 13, 0),
        to_date=_dt(2026, 3, 18, 16, 30),
        location_id=lewes.id,
        comments="Police issued Section 35 order. Group dispersed without arrest.",
    )
    db.session.add(inc2_evt)
    db.session.flush()
    inc2.events.append(inc2_evt)

    # Tesco bulletin 1: X post
    b_tesco_x = Bulletin()
    b_tesco_x.title = (
        "There's a protest at Lewes Tesco rn!! Same lot from the castle I think "
        "#Lewes #LewesHeritageTrust"
    )
    b_tesco_x.sjac_title = "X post: protest at Tesco Lewes car park — 18 Mar 2026"
    b_tesco_x.description = (
        "X post by account @lewes_local at 13:22 GMT on 18 March 2026. "
        "Reports a group of protesters blocking the loading bay entrance of the "
        "Tesco superstore on Phoenix Causeway. Post includes a photograph showing "
        "approximately 50–60 people holding placards reading 'Save Meridian House' "
        "and 'Lewes Heritage Trust'. Police vehicles visible in the background. "
        "Post received 340 retweets."
    )
    b_tesco_x.originid = "tesco-x-18mar2026-1322"
    b_tesco_x.source_link = "https://x.com/lewes_local/status/9876543210"
    b_tesco_x.publish_date = _dt(2026, 3, 18, 13, 22)
    b_tesco_x.documentation_date = _dt(2026, 3, 18, 15, 0)
    b_tesco_x.reliability_score = 55
    b_tesco_x.comments = (
        "Photograph corroborates presence of Lewes Heritage Trust placards — "
        "same group as castle siege. Account @lewes_local has 1.2k followers, "
        "no prior history of misinformation."
    )
    b_tesco_x.status = status_assigned
    b_tesco_x.user_id = admin.id
    # b_tesco_x.assigned_to_id not set (unassigned)
    b_tesco_x.tags = []
    db.session.add(b_tesco_x)
    db.session.flush()

    b_tesco_x.labels.append(label_map["Lewes Castle Siege"])
    b_tesco_x.locations.append(lewes)
    b_tesco_x.sources.append(sources["X (Twitter)"])
    b_tesco_x.events.append(inc2_evt)

    geo_type_comm2 = GeoLocationType.query.filter_by(title="Commercial/Retail").first()
    geo_tesco = GeoLocation()
    geo_tesco.title = "Tesco Lewes — Phoenix Causeway"
    geo_tesco.latlng = "POINT(0.0147 50.8771)"
    geo_tesco.type_id = geo_type_comm2.id if geo_type_comm2 else None
    geo_tesco.main = True
    geo_tesco.comment = "Tesco superstore car park, Phoenix Causeway. Secondary protest site."
    geo_tesco.bulletin_id = b_tesco_x.id
    db.session.add(geo_tesco)
    db.session.flush()

    # Tesco bulletin 2: Albion Broadcasting mention
    b_tesco_bbc = Bulletin()
    b_tesco_bbc.title = (
        "Lewes Castle siege: secondary protest reported at local supermarket"
    )
    b_tesco_bbc.sjac_title = "Albion Broadcasting: secondary protest at Tesco Lewes — 18 Mar 2026"
    b_tesco_bbc.description = (
        "Albion Broadcasting online article published at 19:10 GMT on 18 March 2026, "
        "as part of its ongoing coverage of the Lewes Castle siege. A paragraph "
        "within the article notes that a secondary group of supporters gathered "
        "at a Lewes supermarket during the afternoon, blocking loading bays before "
        "dispersing following a police order. No arrests were made. The article "
        "identifies the group as affiliated with the Lewes Heritage Trust."
    )
    b_tesco_bbc.originid = "albion-lewes-tesco-protest-18mar2026"
    b_tesco_bbc.source_link = "https://www.albionbroadcasting.co.uk/news/uk-england-sussex-lewes-castle-18mar2026"
    b_tesco_bbc.publish_date = _dt(2026, 3, 18, 19, 10)
    b_tesco_bbc.documentation_date = _dt(2026, 3, 18, 21, 0)
    b_tesco_bbc.reliability_score = 75
    b_tesco_bbc.comments = (
        "Credible national source. Only a brief mention — not the article's focus. "
        "Corroborates X post and confirms no arrests and police dispersal."
    )
    b_tesco_bbc.status = status_assigned
    b_tesco_bbc.user_id = admin.id
    # b_tesco_bbc.assigned_to_id not set (unassigned)
    b_tesco_bbc.tags = []
    db.session.add(b_tesco_bbc)
    db.session.flush()

    b_tesco_bbc.labels.append(label_map["Lewes Castle Siege"])
    b_tesco_bbc.locations.append(lewes)
    b_tesco_bbc.sources.append(sources["Albion Broadcasting"])
    b_tesco_bbc.events.append(inc2_evt)

    pub_evt_tesco_bbc = Event(
        title="Albion Broadcasting reports secondary protest at Tesco Lewes",
        eventtype_id=et_pub.id if et_pub else None,  # Publication
        from_date=_dt(2026, 3, 18, 19, 10),
        to_date=_dt(2026, 3, 18, 19, 10),
        location_id=lewes.id,
    )
    db.session.add(pub_evt_tesco_bbc)
    db.session.flush()
    b_tesco_bbc.events.append(pub_evt_tesco_bbc)

    geo_tesco_bbc = GeoLocation()
    geo_tesco_bbc.title = "Tesco Lewes — Phoenix Causeway"
    geo_tesco_bbc.latlng = "POINT(0.0147 50.8771)"
    geo_tesco_bbc.type_id = geo_type_comm2.id if geo_type_comm2 else None
    geo_tesco_bbc.main = False
    geo_tesco_bbc.comment = "Tesco superstore car park, Phoenix Causeway. Secondary protest site."
    geo_tesco_bbc.bulletin_id = b_tesco_bbc.id
    db.session.add(geo_tesco_bbc)
    db.session.flush()

    # Kieran Moss actor-to-bulletin links (Tesco bulletins)
    atob_m1 = Atob(actor_id=a3.id, bulletin_id=b_tesco_x.id)
    atob_m1.related_as = [4]  # Appeared
    atob_m1.probability = 2  # Certain
    atob_m1.comment = "Moss identifiable at the front of the Tesco protest group in X post image."
    atob_m1.user_id = admin.id
    db.session.add(atob_m1)

    atob_m2 = Atob(actor_id=a3.id, bulletin_id=b_tesco_bbc.id)
    atob_m2.related_as = [4]  # Appeared
    atob_m2.probability = 1  # Probable
    atob_m2.comment = "Albion Broadcasting article corroborates protest; Moss likely present but not named."
    atob_m2.user_id = admin.id
    db.session.add(atob_m2)
    db.session.flush()

    # Itob links for Tesco incident
    for new_b, rel_type, prob, comment in [
        (b_tesco_x, 2, 1, "X post is primary visual evidence of the Tesco protest."),
        (b_tesco_bbc, 3, 1, "Albion Broadcasting corroborates the protest and confirms no arrests."),
    ]:
        db.session.add(Itob(
            incident_id=inc2.id,
            bulletin_id=new_b.id,
            related_as=rel_type,
            probability=prob,
            comment=comment,
            user_id=admin.id,
        ))
    db.session.flush()

    # Kieran Moss → Incident 2 (Participant, Probable)
    itoa_m = Itoa(actor_id=a3.id, incident_id=inc2.id)
    itoa_m.related_as = [5]  # Participant
    itoa_m.probability = 1  # Probable
    itoa_m.comment = "Moss identified at the Tesco protest scene; believed to have led the group."
    itoa_m.user_id = admin.id
    db.session.add(itoa_m)
    db.session.flush()

    # Incident-to-Incident link (castle siege ↔ Tesco protest)
    # Constraint: incident_id < related_incident_id, so inc.id (1) < inc2.id (2)
    itoi = Itoi(incident_id=inc.id, related_incident_id=inc2.id)
    itoi.related_as = 4  # Related
    itoi.probability = 1  # Likely
    itoi.comment = "Tesco protest occurred on day 2 of the siege — same group, same day."
    itoi.user_id = admin.id
    db.session.add(itoi)
    db.session.flush()

    # ── Incident 3: Criminal damage — Meridian House site ───────────
    b_lw1 = Bulletin()
    b_lw1.title = "Police investigating criminal damage at Meridian House demolition site"
    b_lw1.sjac_title = "Lewes & Weald Constabulary: criminal damage at Meridian House site — 22 Mar 2026"
    b_lw1.description = (
        "Press release published by Lewes & Weald Constabulary at 09:15 GMT on "
        "22 March 2026. Officers were called at 06:15 to the Meridian House "
        "demolition site on the Harvey's Brewery site, Lewes, following a report "
        "of criminal damage. On arrival, officers found two excavators with slashed "
        "tyres and protest slogans spray-painted on site hoarding. CCTV cameras "
        "mounted on the hoarding had been obscured with spray paint prior to the "
        "damage, suggesting premeditation. The site had been secured by contractors "
        "the previous afternoon (21 March) in preparation for demolition preparatory "
        "works. No arrests have been made. Lewes & Weald Constabulary are appealing "
        "for witnesses and have opened a criminal damage investigation under reference "
        "CRN/2026/LEW/00389. Anyone with information is asked to call 101."
    )
    b_lw1.originid = "lwc-meridian-damage-22mar2026"
    b_lw1.source_link = "https://www.leweswealdconstabulary.police.uk/news/meridian-house-criminal-damage-22mar2026"
    b_lw1.publish_date = _dt(2026, 3, 22, 9, 15)
    b_lw1.documentation_date = _dt(2026, 3, 24, 10, 0)
    b_lw1.reliability_score = 90
    b_lw1.comments = (
        "Official police source. First documentation of this incident. "
        "Obscuring of CCTV prior to damage indicates planning. "
        "Reference number noted for cross-referencing with future arrest records."
    )
    b_lw1.status = status_assigned
    b_lw1.user_id = admin.id
    # b_lw1.assigned_to_id not set (unassigned)
    b_lw1.tags = []
    db.session.add(b_lw1)
    db.session.flush()

    b_lw1.labels.append(label_map["Lewes Castle Siege"])
    b_lw1.locations.append(lewes)
    b_lw1.sources.append(sources["Lewes & Weald Constabulary"])

    geo_meridian2 = GeoLocation()
    geo_meridian2.title = "Meridian House demolition site"
    geo_meridian2.latlng = "POINT(0.01664 50.87484)"
    geo_meridian2.type_id = geo_type_comm.id if geo_type_comm else None
    geo_meridian2.main = True
    geo_meridian2.comment = "Harvey's Brewery site. Excavators damaged, hoarding spray-painted, CCTV obscured."
    geo_meridian2.bulletin_id = b_lw1.id
    db.session.add(geo_meridian2)
    db.session.flush()

    inc3_evt = Event(
        title="Construction equipment vandalized at Meridian House site",
        eventtype_id=et.id if et else None,  # Incident
        from_date=_dt(2026, 3, 22, 2, 0),
        to_date=_dt(2026, 3, 22, 4, 0),
        location_id=meridian_house.id,
        estimated=True,
    )
    db.session.add(inc3_evt)
    db.session.flush()
    b_lw1.events.append(inc3_evt)

    b_lw2 = Bulletin()
    b_lw2.title = "Demolition site targeted by vandals days after Lewes Castle siege"
    b_lw2.sjac_title = "Lewes Clarion Newspaper: criminal damage at Meridian House site — 22 Mar 2026"
    b_lw2.description = (
        "Lewes Clarion Newspaper online article published at 13:45 GMT on 22 March 2026. "
        "Reports that the Meridian House demolition site on the Harvey's Brewery "
        "site was targeted by vandals in the early hours of 22 March. The article "
        "describes slashed tyres on two excavators and slogans including 'Heritage "
        "Not Rubble' and 'Meridian Lives' spray-painted on site hoarding. The "
        "article quotes the lead contractor, Apex Build Group, confirming the "
        "damage and estimating repair and replacement costs of approximately £18,000. "
        "The Lewes Clarion Newspaper notes the damage occurred three days after seven people "
        "were arrested in connection with the castle occupation and draws an "
        "editorial connection to the Lewes Heritage Trust campaign, though no "
        "group has claimed responsibility. Lewes & Weald Constabulary declined "
        "to confirm whether the damage is being treated as connected to the siege."
    )
    b_lw2.originid = "lc-meridian-damage-22mar2026"
    b_lw2.source_link = "https://www.lewesclarion.co.uk/news/lewes/meridian-house-vandalism-march-2026"
    b_lw2.publish_date = _dt(2026, 3, 22, 13, 45)
    b_lw2.documentation_date = _dt(2026, 3, 24, 11, 0)
    b_lw2.reliability_score = 65
    b_lw2.comments = (
        "Local source. Contractor cost estimate (£18,000) is unverified. "
        "Editorial inference linking damage to Lewes Heritage Trust is speculative "
        "— no group has claimed responsibility. Useful for corroborating the "
        "police account and for the 'Heritage Not Rubble' slogan detail."
    )
    b_lw2.status = status_assigned
    b_lw2.user_id = admin.id
    # b_lw2.assigned_to_id not set (unassigned)
    b_lw2.tags = []
    db.session.add(b_lw2)
    db.session.flush()

    b_lw2.labels.append(label_map["Lewes Castle Siege"])
    b_lw2.locations.append(lewes)
    b_lw2.sources.append(sources["Lewes Clarion Newspaper"])

    geo_meridian3 = GeoLocation()
    geo_meridian3.title = "Meridian House demolition site"
    geo_meridian3.latlng = "POINT(0.01664 50.87484)"
    geo_meridian3.type_id = geo_type_comm.id if geo_type_comm else None
    geo_meridian3.main = False
    geo_meridian3.comment = "Harvey's Brewery site. Scene of criminal damage reported 22 March 2026."
    geo_meridian3.bulletin_id = b_lw2.id
    db.session.add(geo_meridian3)
    db.session.flush()

    b_lw2.events.append(inc3_evt)

    inc3 = Incident()
    inc3.title = "Criminal damage to construction equipment — Meridian House site, Lewes, 22 March 2026"
    inc3.description = (
        "In the early hours of 22 March 2026, persons unknown entered the "
        "Meridian House demolition site at the Harvey's Brewery site in Lewes. "
        "Two excavators had their tyres slashed and protest slogans — including "
        "'Heritage Not Rubble' and 'Meridian Lives' — were spray-painted on site "
        "hoarding. CCTV cameras had been obscured with spray paint prior to the "
        "damage, indicating premeditation. The site had been secured by contractors "
        "the previous afternoon in preparation for demolition preparatory works. "
        "Lewes & Weald Constabulary opened a criminal damage investigation "
        "(CRN/2026/LEW/00389). No arrests have been made. No group has claimed "
        "responsibility. The incident occurred three days after seven people were "
        "arrested in connection with the Lewes Castle occupation."
    )
    inc3.status = status_assigned
    inc3.assigned_to_id = test_users["user1"].id  # Incident ID 3: assigned
    inc3.first_peer_reviewer_id = test_users["user3"].id
    inc3.second_peer_reviewer_id = test_users["user2"].id
    inc3.comments = (
        "Perpetrators unknown. No direct evidence linking this to Thomas Ashdown "
        "or any named individual — Ashdown was on bail at the time. The premeditated "
        "CCTV obstruction suggests familiarity with the site. Possible connection "
        "to Lewes Heritage Trust but unconfirmed. Flagged as potentially linked to "
        "Incident 1 via itoi (Led to) — requires further evidence to confirm."
    )
    db.session.add(inc3)
    db.session.flush()
    inc3.labels.append(label_map["Lewes Castle Siege"])

    pv_cd = PotentialViolation.query.filter_by(title="Criminal Damage").first()
    if pv_cd:
        inc3.potential_violations.append(pv_cd)
    inc3.locations.append(lewes)

    db.session.add(Itob(
        incident_id=inc3.id,
        bulletin_id=b_lw1.id,
        related_as=2,  # Primary Evidence
        probability=2,  # Certain
        comment="Official police report is the primary evidence source for this incident.",
        user_id=admin.id,
    ))
    db.session.add(Itob(
        incident_id=inc3.id,
        bulletin_id=b_lw2.id,
        related_as=3,  # Supporting Evidence
        probability=1,  # Likely
        comment="Lewes Clarion Newspaper corroborates the police account and adds contractor cost estimate and slogan detail.",
        user_id=admin.id,
    ))
    db.session.flush()

    # inc → Led to → inc3 (constraint: incident_id < related_incident_id)
    db.session.add(Itoi(
        incident_id=inc.id,
        related_incident_id=inc3.id,
        related_as=3,  # Led to
        probability=1,  # Likely
        comment="Castle siege publicly identified the Meridian House site as the target; damage followed three days after clearance.",
        user_id=admin.id,
    ))
    db.session.flush()

    # ── Actor-to-Actor relationships ─────────────────────────────────
    # Constraint: actor_id < related_actor_id
    # a.id=1, a2.id=2, a3.id=3

    # Ashdown ↔ Pemberton: Associate, Certain (both named organisers of Lewes Heritage Trust)
    atoa_ap = Atoa(actor_id=a.id, related_actor_id=a2.id)
    atoa_ap.related_as = 9  # Associate
    atoa_ap.probability = 2  # Certain
    atoa_ap.comment = "Both named by The National Courier as leaders of the Lewes Heritage Trust occupation."
    atoa_ap.user_id = admin.id
    db.session.add(atoa_ap)

    # Ashdown ↔ Moss: Associate, Probable (connected via Lewes Heritage Trust)
    atoa_am = Atoa(actor_id=a.id, related_actor_id=a3.id)
    atoa_am.related_as = 9  # Associate
    atoa_am.probability = 1  # Probable
    atoa_am.comment = "Moss identified as a Lewes Heritage Trust volunteer; likely known to Ashdown."
    atoa_am.user_id = admin.id
    db.session.add(atoa_am)

    # Pemberton ↔ Moss: Associate, Probable (connected via Lewes Heritage Trust)
    atoa_pm = Atoa(actor_id=a2.id, related_actor_id=a3.id)
    atoa_pm.related_as = 9  # Associate
    atoa_pm.probability = 1  # Probable
    atoa_pm.comment = "Both connected to Lewes Heritage Trust; Pemberton as Chair, Moss as volunteer."
    atoa_pm.user_id = admin.id
    db.session.add(atoa_pm)

    db.session.flush()

    # ── Media setup ─────
    from enferno.utils.data_helpers import get_file_hash
    import shutil

    media_dir = Media.media_dir
    media_dir.mkdir(parents=True, exist_ok=True)

    # Media for Meridian House bulletin
    src_file = Path(__file__).parent / "meridian-house.png"
    filename = "meridian-house.png"
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
            media.title = "Meridian House demolition illustration"
            media.comments = "Artist's rendering of Meridian House (Grade II listed building) at Harvey's Brewery Site, Lewes"
            media.etag = etag
            cat_photo = MediaCategory.query.filter_by(title="Photo").first()
            if cat_photo:
                media.category_id = cat_photo.id
            media.main = True
            media.user_id = admin.id
            media.bulletin_id = b_pre.id
            db.session.add(media)
    elif not src_file.exists():
        print(f"  Warning: {src_file} not found — no media attached to Meridian House bulletin")

    # ── Media (Lewes Castle photo — stand-in for X post image) ─────
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

    # ── Media (Lewes Castle photo — Facebook post) ──────────────────────
    src_file = Path(__file__).parent / "3-lewes-castle.png"
    filename = "3-lewes-castle.png"
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
            media.title = "Crowd outside Lewes Castle — posted to Facebook by Sandra Brightwell"
            media.comments = "Facebook photograph taken from car window, 17 March 2026 14:35 GMT"
            media.etag = etag
            cat_photo = MediaCategory.query.filter_by(title="Photo").first()
            if cat_photo:
                media.category_id = cat_photo.id
            media.main = True
            media.user_id = admin.id
            media.bulletin_id = b_fb.id
            db.session.add(media)
    elif not src_file.exists():
        print(f"  Warning: {src_file} not found — no media attached to Facebook bulletin")

    # ── Media (Lewes Castle photo — Instagram post) ──────────────────────
    src_file = Path(__file__).parent / "4-history-under-siege.png"
    filename = "4-history-under-siege.png"
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
            media.title = "History under siege — Lewes Castle barbican — posted to Instagram by @historic_lewes"
            media.comments = "Instagram photograph from elevated angle, 17 March 2026 14:41 GMT"
            media.etag = etag
            cat_photo = MediaCategory.query.filter_by(title="Photo").first()
            if cat_photo:
                media.category_id = cat_photo.id
            media.main = True
            media.user_id = admin.id
            media.bulletin_id = b_ig.id
            db.session.add(media)
    elif not src_file.exists():
        print(f"  Warning: {src_file} not found — no media attached to Instagram bulletin")

    # ── Media (Lewes Castle video — TikTok post) ──────────────────────
    src_file = Path(__file__).parent / "5-castle-video.mp4"
    filename = "5-castle-video.mp4"
    filepath = media_dir / filename

    if not filepath.exists() and src_file.exists():
        shutil.copy2(src_file, filepath)
        print(f"  Copied {filename} to media directory")

    if filepath.exists():
        etag = get_file_hash(str(filepath))
        if not Media.query.filter(Media.etag == etag, Media.deleted.is_not(True)).first():
            media = Media()
            media.media_file = filename
            media.media_file_type = "video/mp4"
            media.title = "Interior footage of crowd inside Lewes Castle grounds — posted to TikTok by @sussex_daily"
            media.comments = "TikTok video from inside the castle, 17 March 2026 15:04 GMT. 47 seconds handheld video."
            media.etag = etag
            cat_video = MediaCategory.query.filter_by(title="Video").first()
            if cat_video:
                media.category_id = cat_video.id
            media.main = True
            media.user_id = admin.id
            media.bulletin_id = b_tt.id
            db.session.add(media)
    elif not src_file.exists():
        print(f"  Warning: {src_file} not found — no media attached to TikTok bulletin")

    # ── Media (Tesco Lewes protest photo — X post) ───────────────────
    src_file = Path(__file__).parent / "11-tesco.png"
    filename = "11-tesco.png"
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
            media.title = "Protest at Tesco Lewes car park — 18 March 2026"
            media.comments = "X post photograph showing protesters with Lewes Heritage Trust placards at Tesco"
            media.etag = etag
            cat_photo = MediaCategory.query.filter_by(title="Photo").first()
            if cat_photo:
                media.category_id = cat_photo.id
            media.main = True
            media.user_id = admin.id
            media.bulletin_id = b_tesco_x.id
            db.session.add(media)
    elif not src_file.exists():
        print(f"  Warning: {src_file} not found — no media attached to Tesco bulletin")

    # ── Media (Demolition site photograph) ────────────────────────────
    src_file = Path(__file__).parent / "14-demolition.png"
    filename = "14-demolition.png"
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
            media.title = "Meridian House demolition site — criminal damage aftermath"
            media.comments = "Photograph of demolition site showing damaged excavators and vandalism, 22 March 2026"
            media.etag = etag
            cat_photo = MediaCategory.query.filter_by(title="Photo").first()
            if cat_photo:
                media.category_id = cat_photo.id
            media.main = True
            media.user_id = admin.id
            media.bulletin_id = b_lw2.id
            db.session.add(media)
    elif not src_file.exists():
        print(f"  Warning: {src_file} not found — no media attached to Demolition bulletin")

    # ── Media (Actor photograph — Thomas Ashdown) ─────────────────────
    src_file = Path(__file__).parent / "actor1-thomas-ashdown.png"
    filename = "actor1-thomas-ashdown.png"
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
            media.title = "Thomas Ashdown — identified in crowd at Lewes Castle"
            media.comments = "Screenshot from X post showing Thomas Ashdown at front of crowd, 17 March 2026"
            media.etag = etag
            cat_photo = MediaCategory.query.filter_by(title="Photo").first()
            if cat_photo:
                media.category_id = cat_photo.id
            media.main = True
            media.user_id = admin.id
            media.actor_id = a.id
            db.session.add(media)
    elif not src_file.exists():
        print(f"  Warning: {src_file} not found — no media attached to Thomas Ashdown")

    # ── Media (Secondary image — Lake 1) ───────────────────────────────
    src_file = Path(__file__).parent / "lake1.jpg"
    filename = "lake1.jpg"
    filepath = media_dir / filename

    if not filepath.exists() and src_file.exists():
        shutil.copy2(src_file, filepath)
        print(f"  Copied {filename} to media directory")

    if filepath.exists():
        etag = get_file_hash(str(filepath))
        if not Media.query.filter(Media.etag == etag, Media.deleted.is_not(True)).first():
            media = Media()
            media.media_file = filename
            media.media_file_type = "image/jpeg"
            media.title = "lake1.jpg"
            media.comments = "Secondary image for Thomas Ashdown"
            media.etag = etag
            cat_photo = MediaCategory.query.filter_by(title="Photo").first()
            if cat_photo:
                media.category_id = cat_photo.id
            media.main = False
            media.user_id = admin.id
            media.actor_id = a.id
            db.session.add(media)
    elif not src_file.exists():
        print(f"  Warning: {src_file} not found — no media attached to Thomas Ashdown")

    # ── Media (Actor photograph — Rachel Pemberton) ────────────────────
    src_file = Path(__file__).parent / "actor2-rachel-pemberton.png"
    filename = "actor2-rachel-pemberton.png"
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
            media.title = "Rachel Pemberton — Chair of Lewes Heritage Trust"
            media.comments = "Photograph of Rachel Pemberton, arrested during castle clearance, 19 March 2026"
            media.etag = etag
            cat_photo = MediaCategory.query.filter_by(title="Photo").first()
            if cat_photo:
                media.category_id = cat_photo.id
            media.main = True
            media.user_id = admin.id
            media.actor_id = a2.id
            db.session.add(media)
    elif not src_file.exists():
        print(f"  Warning: {src_file} not found — no media attached to Rachel Pemberton")

    # ── Media (Actor photograph — Kieran Moss) ──────────────────────────
    src_file = Path(__file__).parent / "actor3-kieran-moss.png"
    filename = "actor3-kieran-moss.png"
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
            media.title = "Kieran Moss — flagged as person of interest"
            media.comments = "Photograph of Kieran Moss, flagged as person of interest in connection with Incident 3"
            media.etag = etag
            cat_photo = MediaCategory.query.filter_by(title="Photo").first()
            if cat_photo:
                media.category_id = cat_photo.id
            media.main = True
            media.user_id = admin.id
            media.actor_id = a3.id
            db.session.add(media)
    elif not src_file.exists():
        print(f"  Warning: {src_file} not found — no media attached to Kieran Moss")

    # ═══════════════════════════════════════════════════════════════════
    # BRIGHTON DOME RALLY — 5 April 2026
    # Sussex Green Alliance rally at Brighton Dome. ~50 counter-protesters
    # blocked the main entrance. One arrest: Dylan Kearney, obstruction.
    # ═══════════════════════════════════════════════════════════════════

    # ── Actor: Dylan Kearney ────────────────────────────────────────
    a_dk = Actor()
    a_dk.name = "Dylan Kearney"
    a_dk.first_name = "Dylan"
    a_dk.last_name = "Kearney"
    a_dk.sex = "Male"
    a_dk.age = "Adult"
    a_dk.civilian = "Civilian"
    a_dk.type = "Person"
    a_dk.occupation = "Barista"
    a_dk.position = "Organiser, Brighton Climate Justice Network"
    a_dk.comments = (
        "Identified in X post image at the front of the counter-protest group "
        "outside Brighton Dome on 5 April 2026. Arrested at 14:47 GMT for "
        "obstruction of a public entrance under s.137 Highways Act 1980. "
        "Released on bail on 6 April. Known to Sussex Police from prior "
        "climate protest activity."
    )
    a_dk.status = status_assigned
    # a_dk.assigned_to_id not set (Actor ID 4: unassigned)
    a_dk.first_peer_reviewer_id = test_users["user2"].id
    a_dk.tags = []
    db.session.add(a_dk)
    db.session.flush()

    profile_dk = ActorProfile()
    profile_dk.actor_id = a_dk.id
    profile_dk.mode = 1
    profile_dk.description = (
        "Brighton-based climate activist. Self-describes as 'climate justice "
        "campaigner'. Active on X as @dylan_climateaction. No prior convictions."
    )
    profile_dk.source_link = "https://twitter.com/dylan_climateaction"
    profile_dk.publish_date = _dt(2026, 4, 5, 14, 47)
    profile_dk.documentation_date = _dt(2026, 4, 6, 10, 0)
    profile_dk.sources.append(sources["X (Twitter)"])
    profile_dk.sources.append(sources["Sussex Police"])
    profile_dk.labels.append(label_map["Brighton Dome Rally"])
    db.session.add(profile_dk)

    # ── Media (Actor photograph — Dylan Kearney) ────────────────────
    src_file = Path(__file__).parent / "actor4-dylan-kearney.png"
    filename = "actor4-dylan-kearney.png"
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
            media.title = "Dylan Kearney — arrested at Brighton Dome counter-protest"
            media.comments = "Photograph of Dylan Kearney, identified at Brighton Dome counter-protest, 5 April 2026"
            media.etag = etag
            cat_photo = MediaCategory.query.filter_by(title="Photo").first()
            if cat_photo:
                media.category_id = cat_photo.id
            media.main = True
            media.user_id = admin.id
            media.actor_id = a_dk.id
            db.session.add(media)
    elif not src_file.exists():
        print(f"  Warning: {src_file} not found — no media attached to Dylan Kearney")

    # ── Bulletins ──────────────────────────────────────────────────

    # Bulletin 1: The Argus article
    b_argus = Bulletin()
    b_argus.title = "Protesters block entrance to Brighton Dome climate rally"
    b_argus.sjac_title = "The Argus: counter-protest at Brighton Dome rally — 5 Apr 2026"
    b_argus.description = (
        "The Argus online article published at 16:30 GMT on 5 April 2026. "
        "Reports that approximately 50 counter-protesters gathered outside "
        "Brighton Dome during a Sussex Green Alliance climate rally, blocking "
        "the main entrance on Church Street for around 20 minutes. Police were "
        "called at 14:30 and a Section 35 dispersal direction was issued under "
        "the Anti-social Behaviour, Crime and Policing Act 2014. One man, "
        "named as Dylan Kearney, 28, of Brighton, was arrested on suspicion "
        "of obstruction of a public entrance. He was released on bail the "
        "following morning. The Sussex Green Alliance rally continued inside "
        "the Dome and concluded without further incident."
    )
    b_argus.originid = "argus-brighton-dome-rally-05apr2026"
    b_argus.source_link = "https://www.theargus.co.uk/news/brighton/2026/apr/05/brighton-dome-protest-arrest"
    b_argus.publish_date = _dt(2026, 4, 5, 16, 30)
    b_argus.documentation_date = _dt(2026, 4, 6, 9, 0)
    b_argus.reliability_score = 80
    b_argus.comments = (
        "Credible regional newspaper. Names Kearney directly. "
        "Article quotes a Sussex Police spokesperson — corroborates the police statement."
    )
    b_argus.status = status_assigned
    b_argus.user_id = admin.id
    # b_argus.assigned_to_id not set (unassigned)
    b_argus.tags = []
    db.session.add(b_argus)
    db.session.flush()
    b_argus.labels.append(label_map["Brighton Dome Rally"])
    b_argus.locations.append(brighton_dome)
    b_argus.sources.append(sources["The Argus"])

    geo_dome_argus = GeoLocation()
    geo_dome_argus.title = "Brighton Dome — Church Street entrance"
    geo_dome_argus.latlng = "POINT(-0.1390 50.8237)"
    geo_dome_argus.type_id = GeoLocationType.query.filter_by(title="Government Building").first()
    geo_dome_argus.type_id = geo_dome_argus.type_id.id if geo_dome_argus.type_id else None
    geo_dome_argus.main = True
    geo_dome_argus.comment = "Victorian concert hall and conference venue. Counter-protesters blocked Church Street entrance."
    geo_dome_argus.bulletin_id = b_argus.id
    db.session.add(geo_dome_argus)
    db.session.flush()

    # Bulletin 2: X post
    b_dome_x = Bulletin()
    b_dome_x.title = "Counter-protesters outside Brighton Dome right now — police just arrived #BrightonDome #ClimateJustice"
    b_dome_x.sjac_title = "X post: crowd outside Brighton Dome — 5 Apr 2026"
    b_dome_x.description = (
        "X post by account @brighton_witness at 14:38 GMT on 5 April 2026. "
        "Accompanied by a photograph showing approximately 40–50 people "
        "blocking the Church Street entrance to Brighton Dome, several holding "
        "placards reading 'No Greenwash' and 'Real Action Now'. Two Sussex "
        "Police officers visible at the edge of the crowd. Post received "
        "1,200 retweets before the account was set to protected."
    )
    b_dome_x.originid = "x-brighton-dome-protest-05apr2026"
    b_dome_x.source_link = "https://twitter.com/brighton_witness/status/1908234567890123456"
    b_dome_x.publish_date = _dt(2026, 4, 5, 14, 38)
    b_dome_x.documentation_date = _dt(2026, 4, 5, 17, 0)
    b_dome_x.reliability_score = 60
    b_dome_x.comments = (
        "Account set to protected shortly after — screenshot and metadata preserved. "
        "Dylan Kearney identifiable at the front of the group."
    )
    b_dome_x.status = status_assigned
    b_dome_x.user_id = admin.id
    # b_dome_x.assigned_to_id not set (unassigned)
    b_dome_x.tags = []
    db.session.add(b_dome_x)
    db.session.flush()
    b_dome_x.labels.append(label_map["Brighton Dome Rally"])
    b_dome_x.locations.append(brighton_dome)
    b_dome_x.sources.append(sources["X (Twitter)"])

    # ── Media (Brighton Dome counter-protesters photo — X post) ─────────
    src_file = Path(__file__).parent / "16-counter-protesters-dome.png"
    filename = "16-counter-protesters-dome.png"
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
            media.title = "Counter-protesters outside Brighton Dome — 5 April 2026"
            media.comments = "X post photograph showing counter-protesters at Brighton Dome entrance with placards"
            media.etag = etag
            cat_photo = MediaCategory.query.filter_by(title="Photo").first()
            if cat_photo:
                media.category_id = cat_photo.id
            media.main = True
            media.user_id = admin.id
            media.bulletin_id = b_dome_x.id
            db.session.add(media)
    elif not src_file.exists():
        print(f"  Warning: {src_file} not found — no media attached to Brighton Dome bulletin")

    # Bulletin 3: Sussex Police statement
    b_dome_sp = Bulletin()
    b_dome_sp.title = "Sussex Police: one arrested following Brighton Dome disturbance — 5 April 2026"
    b_dome_sp.sjac_title = "Sussex Police press statement: Brighton Dome arrest — 5 Apr 2026"
    b_dome_sp.description = (
        "Press statement published by Sussex Police at 18:00 GMT on 5 April 2026. "
        "\n\n"
        "\"Officers attended Brighton Dome, Church Street, Brighton at approximately "
        "14:30 following reports of a group blocking the public entrance. A Section 35 "
        "dispersal direction was issued under the Anti-social Behaviour, Crime and "
        "Policing Act 2014. One man, aged 28, was arrested on suspicion of obstruction "
        "of a public entrance. He has been released on bail pending further enquiries. "
        "The remainder of the group dispersed without further incident by 15:10. "
        "Sussex Police would like to thank members of the public for their patience.\""
    )
    b_dome_sp.originid = "sussex-police-dome-arrest-05apr2026"
    b_dome_sp.source_link = "https://www.sussex.police.uk/news/brighton-dome-disturbance-05apr2026"
    b_dome_sp.publish_date = _dt(2026, 4, 5, 18, 0)
    b_dome_sp.documentation_date = _dt(2026, 4, 6, 9, 30)
    b_dome_sp.reliability_score = 90
    b_dome_sp.comments = (
        "Official police statement — high reliability. Confirms arrest, Section 35, "
        "and dispersal timeline. Does not name Kearney but The Argus article does."
    )
    b_dome_sp.status = status_assigned
    b_dome_sp.user_id = admin.id
    # b_dome_sp.assigned_to_id not set (unassigned)
    b_dome_sp.tags = []
    db.session.add(b_dome_sp)
    db.session.flush()
    b_dome_sp.labels.append(label_map["Brighton Dome Rally"])
    b_dome_sp.locations.append(brighton_dome)
    b_dome_sp.sources.append(sources["Sussex Police"])

    # ── Incident ───────────────────────────────────────────────────
    inc_dome = Incident()
    inc_dome.title = "Counter-protest and arrest at Brighton Dome — 5 April 2026"
    inc_dome.description = (
        "Approximately 50 counter-protesters affiliated with Brighton Climate "
        "Justice Network blocked the Church Street entrance to Brighton Dome "
        "during a Sussex Green Alliance climate rally. Police issued a Section 35 "
        "dispersal order. One arrest: Dylan Kearney, for obstruction."
    )
    inc_dome.status = status_assigned
    # inc_dome.assigned_to_id not set (Incident ID 4: unassigned)
    inc_dome.comments = "Linked to broader Sussex Green Alliance activity. Monitor for charge/bail outcome."
    db.session.add(inc_dome)
    db.session.flush()
    inc_dome.labels.append(label_map["Brighton Dome Rally"])

    # Actor-to-bulletin links
    atob_dk1 = Atob(actor_id=a_dk.id, bulletin_id=b_dome_x.id)
    atob_dk1.related_as = [4]  # Appeared
    atob_dk1.probability = 2   # Certain
    atob_dk1.comment = "Kearney identifiable at the front of the group in the X post image."
    atob_dk1.user_id = admin.id
    db.session.add(atob_dk1)

    atob_dk2 = Atob(actor_id=a_dk.id, bulletin_id=b_argus.id)
    atob_dk2.related_as = [4]  # Appeared
    atob_dk2.probability = 2   # Certain
    atob_dk2.comment = "Named directly in The Argus article as the arrested individual."
    atob_dk2.user_id = admin.id
    db.session.add(atob_dk2)
    db.session.flush()

    # Incident-to-bulletin links
    for new_b, rel_type, prob, comment in [
        (b_dome_x,  2, 2, "X post is primary visual evidence of the blockade."),
        (b_argus,   2, 2, "Argus article names the arrested individual and confirms timeline."),
        (b_dome_sp, 3, 2, "Sussex Police statement confirms arrest and Section 35 dispersal."),
    ]:
        db.session.add(Itob(
            incident_id=inc_dome.id,
            bulletin_id=new_b.id,
            related_as=rel_type,
            probability=prob,
            comment=comment,
            user_id=admin.id,
        ))

    # Incident-to-actor link
    itoa_dk = Itoa(actor_id=a_dk.id, incident_id=inc_dome.id)
    itoa_dk.related_as = [5]  # Participant
    itoa_dk.probability = 2   # Certain
    itoa_dk.comment = "Kearney arrested at the scene — confirmed participant."
    itoa_dk.user_id = admin.id
    db.session.add(itoa_dk)
    db.session.flush()

    # ── Apply OVRM ID values to all bulletins ────────────────────────
    ovrm_ids = {
        b_pre:       "OVRM/2026/B/001",
        b:           "OVRM/2026/B/002",
        b_fb:        "OVRM/2026/B/003",
        b_ig:        "OVRM/2026/B/004",
        b_tt:        "OVRM/2026/B/005",
        b_ew:        "OVRM/2026/B/006",
        b_bbc:       "OVRM/2026/B/007",
        b_sp:        "OVRM/2026/B/008",
        b_grdn:      "OVRM/2026/B/009",
        b_sp2:       "OVRM/2026/B/010",
        b_tesco_x:   "OVRM/2026/B/011",
        b_tesco_bbc: "OVRM/2026/B/012",
        b_lw1:       "OVRM/2026/B/013",
        b_lw2:       "OVRM/2026/B/014",
        b_argus:     "OVRM/2026/B/015",
        b_dome_x:    "OVRM/2026/B/016",
        b_dome_sp:   "OVRM/2026/B/017",
    }
    for bulletin, ovrm_id_val in ovrm_ids.items():
        DynamicField.apply_values(bulletin, {"ovrm_id": ovrm_id_val})

    db.session.commit()

    print("Minimal demo data seeded successfully!")
    print(f"  Test users: user1/user1pass (Analyst One), user2/user2pass (Analyst Two), user3/user3pass (Analyst Three)")
    print(f"  Sources:    {len(source_titles)} ({', '.join(source_titles)})")
    print(f"  Locations:  5 (East Sussex → Lewes → Lewes Castle, Meridian House | Brighton → Brighton Dome)")
    print(f"  Actors:     4 (Thomas Ashdown | Rachel Pemberton | Kieran Moss | Dylan Kearney)")
    print(f"  Bulletins:  17 (OVRM/2026/B/001–017, OVRM ID field set)")
    print(f"    [Lewes Castle Siege]")
    print(f"    - Lewes Clarion Newspaper: council approves Meridian House demolition — 3 Mar (assigned user1, context)")
    print(f"    - X post (assigned user1)")
    print(f"    - Facebook caption (assigned user2)")
    print(f"    - Instagram caption (assigned user3)")
    print(f"    - TikTok caption (assigned user1)")
    print(f"    - Eyewitness statement / Margaret Okafor (assigned user2)")
    print(f"    - Albion Broadcasting article: day 2 (assigned user3)")
    print(f"    - Lewes & Weald Constabulary statement: day 2 (assigned user1)")
    print(f"    - The National Courier article: day 3 (assigned user2)")
    print(f"    - Lewes & Weald Constabulary statement: day 3 (assigned user3)")
    print(f"    - X post: Tesco Lewes car park protest (assigned user2)")
    print(f"    - Albion Broadcasting: Tesco protest mention (assigned user3)")
    print(f"    - Lewes & Weald Constabulary: criminal damage at Meridian House (assigned user3)")
    print(f"    - Lewes Clarion Newspaper: criminal damage at Meridian House (assigned user1)")
    print(f"    [Brighton Dome Rally]")
    print(f"    - The Argus: counter-protest at Brighton Dome (assigned user2)")
    print(f"    - X post: crowd outside Brighton Dome (assigned user3)")
    print(f"    - Sussex Police statement: one arrest (assigned user1)")
    print(f"  Incidents:  4 (Lewes Castle occupation | Phoenix Causeway assembly | Meridian House criminal damage | Brighton Dome counter-protest)")
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

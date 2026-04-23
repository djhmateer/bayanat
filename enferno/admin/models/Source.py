import json
from tempfile import NamedTemporaryFile
from typing import Any, Optional

import pandas as pd
import werkzeug
from sqlalchemy import text

import enferno.utils.typing as t
from enferno.extensions import db
from enferno.utils.base import BaseMixin
from enferno.utils.date_helper import DateHelper
from enferno.utils.logging_utils import get_logger

logger = get_logger()


class Source(db.Model, BaseMixin):
    """
    SQL Alchemy model for sources
    """

    __table_args__ = {"extend_existing": True}

    id = db.Column(db.Integer, primary_key=True)
    etl_id = db.Column(db.String, unique=True)
    title = db.Column(db.String, index=True)
    title_ar = db.Column(db.String, index=True)
    source_type = db.Column(db.String)
    comments = db.Column(db.Text)
    comments_ar = db.Column(db.Text)
    url = db.Column(db.String)
    locked = db.Column(db.Boolean, default=False)
    account_focus = db.Column(db.String)
    parent_id = db.Column(db.Integer, db.ForeignKey("source.id"), index=True)
    parent = db.relationship("Source", remote_side=id, backref="sub_source")

    def from_json(self, json: dict[str, Any]) -> "Source":
        self.title = json["title"]
        if "title_ar" in json:
            self.title_ar = json["title_ar"]
        if "comments" in json:
            self.comments = json["comments"]
        if "comments_ar" in json:
            self.comments = json["comments_ar"]
        if "url" in json:
            self.url = json["url"] or None
        if "locked" in json:
            self.locked = bool(json["locked"])
        if "account_focus" in json:
            self.account_focus = json["account_focus"] or None
        parent = json.get("parent")
        if parent:
            parent_id = parent.get("id")
            # Prevent self-reference and circular parent assignment
            if parent_id and parent_id != self.id:
                p_source = db.session.get(Source, parent_id)
                if p_source and (not p_source.parent_id or p_source.parent_id != self.id):
                    self.parent_id = parent_id
                else:
                    self.parent_id = None
            else:
                self.parent_id = None
        else:
            self.parent_id = None
        return self

    def to_dict(self) -> dict[str, Any]:
        """Return a dictionary representation of the source."""
        return {
            "id": self.id,
            "title": self.title,
            "etl_id": self.etl_id,
            "parent": {"id": self.parent.id, "title": self.parent.title} if self.parent else None,
            "comments": self.comments,
            "url": self.url,
            "locked": self.locked or False,
            "account_focus": self.account_focus,
            "updated_at": (
                DateHelper.serialize_datetime(self.updated_at) if self.updated_at else None
            ),
        }

    def __repr__(self) -> str:
        return "<Source {} {}>".format(self.id, self.title)

    def to_json(self) -> str:
        """Return a JSON representation of the source."""
        return json.dumps(self.to_dict())

    @staticmethod
    def find_by_ids(ids: list[t.id]) -> list[dict[str, Any]]:
        """
        finds all items and subitems of a given list of ids, using raw sql query instead of the orm.

        Args:
            - ids: list of ids to search for.

        Returns:
            - matching records
        """
        if not ids:
            return []
        qstr = tuple(ids)
        query = """
               with  recursive lcte (id, parent_id, title) as (
               select id, parent_id, title from source where id in :qstr union all 
               select x.id, x.parent_id, x.title from lcte c, source x where x.parent_id = c.id)
               select * from lcte;
               """
        with db.engine.connect() as connection:
            result = connection.execute(text(query), {"qstr": qstr})
            return [{"id": x[0], "title": x[2]} for x in result]

    @staticmethod
    def get_children(sources: list, depth: int = 3) -> list:
        """
        Retrieves the children of the given sources up to a specified depth.

        Args:
            - sources: list of sources to retrieve children for.
            - depth: the depth of the search.

        Returns:
            - list of children sources.
        """
        all = []
        targets = sources
        while depth != 0:
            children = Source.get_direct_children(targets)
            all += children
            targets = children
            depth -= 1
        return all

    @staticmethod
    def get_direct_children(sources: list) -> list:
        """
        Retrieves the direct children of the given sources.

        Args:
            - sources: list of sources to retrieve children for.

        Returns:
            - list of children sources.
        """
        children = []
        for source in sources:
            children += source.sub_source
        return children

    @staticmethod
    def find_by_title(title: str) -> Optional["Source"]:
        """
        Finds a source by its title.

        Args:
            - title: the title of the source.

        Returns:
            - the source object.
        """
        ar = Source.query.filter(Source.title_ar.ilike(title)).first()
        if ar:
            return ar
        else:
            return Source.query.filter(Source.title.ilike(title)).first()

    @staticmethod
    def import_csv(file_storage: werkzeug.datastructures.FileStorage) -> str:
        """
        Imports Source data from a CSV file.

        Args:
            - file_storage: the file storage object containing the CSV data.

        Returns:
            - empty string on success.
        """
        tmp = NamedTemporaryFile().name
        file_storage.save(tmp)
        df = pd.read_csv(tmp)
        df.columns = [c.lower() for c in df.columns]

        logger.info(f"Source CSV import: {len(df)} rows, columns: {list(df.columns)}")

        # Truncate existing sources before re-import
        db.session.execute(text("TRUNCATE TABLE source RESTART IDENTITY CASCADE"))
        db.session.commit()
        logger.info("Source table truncated")

        # Keep only columns that exist on the Source table
        valid_cols = {c.name for c in Source.__table__.columns}
        extra_cols = [c for c in df.columns if c not in valid_cols]
        if extra_cols:
            logger.warning(f"Ignoring unrecognised CSV columns: {extra_cols}")
        df = df[[c for c in df.columns if c in valid_cols]]

        # Drop rows with no title
        if "title" in df.columns:
            before = len(df)
            df = df[df.title.notna() & (df.title.astype(str).str.strip() != "")]
            dropped = before - len(df)
            if dropped:
                logger.warning(f"Dropped {dropped} rows with missing title")

        # Normalise nullable fields
        if "comments" in df.columns:
            df.comments = df.comments.fillna("")
        if "url" in df.columns:
            df.url = df.url.where(df.url.notna(), None)
        if "locked" in df.columns:
            df.locked = df.locked.fillna(False).astype(bool)

        logger.info(f"Attempting to insert {len(df)} rows after filtering")

        # Insert row-by-row using savepoints so a single bad row doesn't abort others
        imported = 0
        skipped = 0
        for i, record in enumerate(df.to_dict(orient="records")):
            try:
                with db.session.begin_nested():
                    db.session.execute(Source.__table__.insert().values(**record))
                imported += 1
            except Exception as e:
                skipped += 1
                logger.error(f"Row {i+1} skipped — {type(e).__name__}: {e} | data: {record}")

        db.session.commit()

        # reset id sequence counter
        max_id = db.session.execute(text("select max(id)+1 from source")).scalar()
        db.session.execute(text("alter sequence source_id_seq restart with :m"), {"m": max_id})
        db.session.commit()

        logger.info(f"Source import complete: {imported} inserted, {skipped} skipped")
        return f"Imported {imported} sources ({skipped} skipped)"

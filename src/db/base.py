"""
db/base.py
-----------
Single source of truth for the SQLAlchemy DeclarativeBase.

All ORM models import ``Base`` from here so that
``Base.metadata.create_all()`` can discover every table in the application.

SQLAlchemy 2.0 style
─────────────────────
Uses ``DeclarativeBase`` (not the legacy ``declarative_base()`` factory)
so mapped columns benefit from full type-checking support.

Import order
────────────
main.py / create_all_tables() must import ``db.models`` (or any other model
module) *before* calling ``Base.metadata.create_all()`` so the table
definitions are registered with the metadata.  This is handled automatically
by the ``db/__init__.py`` wildcard import below.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """
    Shared declarative base for every Koda ORM model.

    All subclasses are automatically registered in ``Base.metadata``
    when their module is imported.
    """
    pass

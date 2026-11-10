"""Base declarativa compartida por todos los modelos ORM."""
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base declarativa (SQLAlchemy 2.0) para todas las tablas del dominio."""
    pass
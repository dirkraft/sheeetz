from sqlalchemy import Column, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    google_id = Column(String, unique=True, nullable=False, index=True)
    email = Column(String, nullable=False)
    name = Column(String, nullable=False)
    drive_token_json = Column(Text, nullable=True)

    sheets = relationship("Sheet", back_populates="user", cascade="all, delete-orphan")
    library_folders = relationship("LibraryFolder", back_populates="user", cascade="all, delete-orphan")


class Sheet(Base):
    __tablename__ = "sheets"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    drive_file_id = Column(String, nullable=True, index=True)
    filename = Column(String, nullable=False)
    folder_path = Column(String, nullable=True)

    user = relationship("User", back_populates="sheets")
    metadata_entries = relationship("SheetMeta", back_populates="sheet", cascade="all, delete-orphan")


class SheetMeta(Base):
    __tablename__ = "sheet_meta"

    id = Column(Integer, primary_key=True)
    sheet_id = Column(Integer, ForeignKey("sheets.id"), nullable=False, index=True)
    key = Column(String, nullable=False, index=True)
    value = Column(Text, nullable=False)

    sheet = relationship("Sheet", back_populates="metadata_entries")


class LibraryFolder(Base):
    __tablename__ = "library_folders"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    backend_type = Column(String, nullable=False)  # "local" or "gdrive"
    backend_folder_id = Column(String, nullable=False)  # absolute path or Drive folder ID
    folder_name = Column(String, nullable=False)
    folder_path = Column(String, nullable=False, default="/")

    user = relationship("User", back_populates="library_folders")

    __table_args__ = (
        UniqueConstraint("user_id", "backend_type", "backend_folder_id", name="uq_user_folder"),
    )

"""
Backup manager for old_code directory.

Manages backup copies of files with UUID-based indexing and version tracking.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = None


def _get_logger():
    """Lazy import logger to avoid circular imports."""
    global logger
    if logger is None:
        import logging

        logger = logging.getLogger(__name__)
    return logger


class BackupManager:
    """Manages backup copies of files in old_code directory."""

    def __init__(self, root_dir: Path) -> None:
        """
        Initialize backup manager.

        Args:
            root_dir: Project root directory
        """
        self.root_dir = Path(root_dir).resolve()
        self.backup_dir = self.root_dir / "old_code"
        self.index_file = self.backup_dir / "index.txt"
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def _load_index(self) -> Dict[str, Dict[str, str]]:
        """
        Load index from file.

        Format: UUID|File Path|Timestamp|Command|Related Files|Comment

        Returns:
            Dictionary mapping UUID to backup info
        """
        # Ensure backup directory exists (in case it was deleted)
        self.backup_dir.mkdir(parents=True, exist_ok=True)

        if not self.index_file.exists():
            return {}

        index: Dict[str, Dict[str, str]] = {}
        try:
            with open(self.index_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    parts = line.split("|")
                    if len(parts) >= 3:
                        backup_uuid = parts[0]
                        file_path = parts[1]
                        timestamp = parts[2]
                        command = parts[3] if len(parts) > 3 else ""
                        related_files = parts[4] if len(parts) > 4 else ""
                        comment = parts[5] if len(parts) > 5 else ""
                        index[backup_uuid] = {
                            "file_path": file_path,
                            "timestamp": timestamp,
                            "command": command,
                            "related_files": related_files,
                            "comment": comment,
                        }
        except Exception as e:
            _get_logger().error(f"Error loading index: {e}")
        return index

    def _save_index(self, index: Dict[str, Dict[str, str]]) -> None:
        """
        Save index to file.

        Format: UUID|File Path|Timestamp|Command|Related Files|Comment

        Args:
            index: Dictionary mapping UUID to backup info
        """
        try:
            # Ensure backup directory exists (in case it was deleted)
            self.backup_dir.mkdir(parents=True, exist_ok=True)
            with open(self.index_file, "w", encoding="utf-8") as f:
                f.write("# UUID|File Path|Timestamp|Command|Related Files|Comment\n")
                for backup_uuid, info in sorted(index.items()):
                    command = info.get("command", "")
                    related_files = info.get("related_files", "")
                    comment = info.get("comment", "")
                    f.write(
                        f"{backup_uuid}|{info['file_path']}|{info['timestamp']}|{command}|{related_files}|{comment}\n"
                    )
        except Exception as e:
            _get_logger().error(f"Error saving index: {e}")

    def _generate_backup_filename(self, original_path: Path, backup_uuid: str) -> str:
        """
        Generate backup filename.

        Format: Исходный_путь_и_имя_файла_с_расширением-UUID4

        Args:
            original_path: Original file path (absolute or relative)
            backup_uuid: UUID for this backup

        Returns:
            Backup filename
        """
        # Convert to relative path if absolute
        if original_path.is_absolute():
            try:
                path_str = str(original_path.relative_to(self.root_dir))
            except ValueError:
                # If not relative to root_dir, use full path
                path_str = str(original_path)
        else:
            path_str = str(original_path)

        # Convert path to string with underscores
        path_str = path_str.replace("/", "_").replace("\\", "_")
        # Remove leading underscores
        path_str = path_str.lstrip("_")
        return f"{path_str}-{backup_uuid}"

    def create_backup(
        self,
        file_path: Path,
        command: str = "",
        related_files: Optional[List[str]] = None,
        comment: str = "",
    ) -> Optional[str]:
        """
        Create backup copy of file.

        Args:
            file_path: Path to file to backup (absolute or relative to root_dir)
            command: Name of command that triggered backup
            related_files: List of related files (e.g., files created from split)
            comment: Optional comment/message for this backup

        Returns:
            UUID of created backup, or None if failed
        """
        try:
            # Resolve file path
            if not file_path.is_absolute():
                file_path = self.root_dir / file_path
            file_path = file_path.resolve()

            if not file_path.exists():
                _get_logger().warning(f"File not found: {file_path}")
                return None

            # Ensure backup directory exists (in case it was deleted)
            self.backup_dir.mkdir(parents=True, exist_ok=True)

            # Generate UUID and backup filename
            backup_uuid = str(uuid.uuid4())
            backup_filename = self._generate_backup_filename(file_path, backup_uuid)
            backup_path = self.backup_dir / backup_filename

            # Copy file
            shutil.copy2(file_path, backup_path)

            # Get file modification time
            mtime = file_path.stat().st_mtime
            timestamp = datetime.fromtimestamp(mtime).strftime("%Y-%m-%dT%H-%M-%S")

            # Update index with relative path
            try:
                relative_path = str(file_path.relative_to(self.root_dir))
            except ValueError:
                # If not relative to root_dir, use absolute path
                relative_path = str(file_path)

            # Prepare related files string
            related_files_str = ",".join(related_files) if related_files else ""

            # Update index
            index = self._load_index()
            index[backup_uuid] = {
                "file_path": relative_path,
                "timestamp": timestamp,
                "command": command,
                "related_files": related_files_str,
                "comment": comment,
            }
            self._save_index(index)

            _get_logger().info(f"Backup created: {backup_path.name} ({backup_uuid})")
            return backup_uuid
        except Exception as e:
            _get_logger().error(f"Error creating backup: {e}")
            return None

    def list_files(self) -> List[Dict[str, str]]:
        """
        List all backed up files (unique original paths).

        Returns:
            List of dictionaries with file_path
        """
        index = self._load_index()
        files = {}
        for backup_uuid, info in index.items():
            file_path = info["file_path"]
            if file_path not in files:
                files[file_path] = {"file_path": file_path}
        return list(files.values())

    def list_versions(self, file_path: str) -> List[Dict[str, Any]]:
        """
        List all versions of a file.

        Args:
            file_path: Original file path (relative to root_dir)

        Returns:
            List of dictionaries with uuid, timestamp, size_bytes, size_lines
        """
        index = self._load_index()
        versions = []

        # Normalize search path
        search_path = file_path.replace("\\", "/")

        for backup_uuid, info in index.items():
            # Normalize index path
            index_path = info["file_path"].replace("\\", "/")
            if index_path == search_path:
                # Find backup file - use path from index
                backup_filename = self._generate_backup_filename(
                    Path(info["file_path"]), backup_uuid
                )
                backup_path = self.backup_dir / backup_filename

                if backup_path.exists():
                    stat = backup_path.stat()
                    size_bytes = stat.st_size

                    # Count lines
                    try:
                        with open(backup_path, "r", encoding="utf-8") as f:
                            size_lines = len(f.readlines())
                    except Exception:
                        size_lines = 0

                    version_info = {
                        "uuid": backup_uuid,
                        "timestamp": info["timestamp"],
                        "size_bytes": size_bytes,
                        "size_lines": size_lines,
                        "command": info.get("command", ""),
                        "comment": info.get("comment", ""),
                        "related_files": (
                            info.get("related_files", "").split(",")
                            if info.get("related_files")
                            else []
                        ),
                    }
                    versions.append(version_info)

        # Sort by timestamp (newest first); key must be comparable (str)
        versions.sort(
            key=lambda x: str(x.get("timestamp", "")),
            reverse=True,
        )
        return versions

    def restore_file(
        self, file_path: str, backup_uuid: Optional[str] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Restore file from backup.

        Args:
            file_path: Original file path (relative to root_dir)
            backup_uuid: UUID of backup to restore (if None, restore latest)

        Returns:
            Tuple of (success, message)
        """
        try:
            versions = self.list_versions(file_path)
            if not versions:
                return (False, f"No backups found for {file_path}")

            # Find backup to restore
            if backup_uuid:
                backup_info = next(
                    (v for v in versions if v["uuid"] == backup_uuid), None
                )
                if not backup_info:
                    return (False, f"Backup {backup_uuid} not found")
            else:
                # Use latest
                backup_info = versions[0]

            # Find backup file
            backup_filename = self._generate_backup_filename(
                Path(file_path), backup_info["uuid"]
            )
            backup_path = self.backup_dir / backup_filename

            if not backup_path.exists():
                return (False, f"Backup file not found: {backup_path}")

            # Restore to original location (mandatory backup of current file first)
            target_path = self.root_dir / file_path
            if target_path.exists():
                backup_uuid_before = self.create_backup(
                    target_path,
                    command="restore_backup_file",
                    comment="Before restore from backup",
                )
                if not backup_uuid_before:
                    _get_logger().warning(
                        "Failed to create backup of current file before restore"
                    )
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup_path, target_path)

            _get_logger().info(f"File restored: {file_path} from {backup_info['uuid']}")
            return (True, f"File restored from backup {backup_info['uuid']}")
        except Exception as e:
            _get_logger().error(f"Error restoring file: {e}")
            return (False, str(e))

    def delete_backup(self, backup_uuid: str) -> Tuple[bool, Optional[str]]:
        """
        Delete specific backup.

        Args:
            backup_uuid: UUID of backup to delete

        Returns:
            Tuple of (success, message)
        """
        try:
            index = self._load_index()
            if backup_uuid not in index:
                return (False, f"Backup {backup_uuid} not found in index")

            info = index[backup_uuid]
            file_path = info["file_path"]

            # Find and delete backup file
            backup_filename = self._generate_backup_filename(
                Path(file_path), backup_uuid
            )
            backup_path = self.backup_dir / backup_filename

            if backup_path.exists():
                backup_path.unlink()

            # Remove from index
            del index[backup_uuid]
            self._save_index(index)

            _get_logger().info(f"Backup deleted: {backup_uuid}")
            return (True, f"Backup {backup_uuid} deleted")
        except Exception as e:
            _get_logger().error(f"Error deleting backup: {e}")
            return (False, str(e))

    def clear_all(self) -> Tuple[bool, Optional[str]]:
        """
        Clear all backups and index.

        Returns:
            Tuple of (success, message)
        """
        try:
            # Ensure backup directory exists
            self.backup_dir.mkdir(parents=True, exist_ok=True)

            # Delete all backup files
            for backup_file in self.backup_dir.glob("*"):
                if backup_file.is_file() and backup_file.name != "index.txt":
                    backup_file.unlink()

            # Clear index
            self._save_index({})

            _get_logger().info("All backups cleared")
            return (True, "All backups cleared")
        except Exception as e:
            _get_logger().error(f"Error clearing backups: {e}")
            return (False, str(e))

    def create_database_backup(
        self,
        db_path: Path,
        backup_dir: Path,
        comment: str = "Schema synchronization backup",
    ) -> Optional[str]:
        """
        Create backup of database file and sidecar files.

        Args:
            db_path: Path to database file
            backup_dir: Directory where to store backups
            comment: Optional comment for backup

        Returns:
            UUID of created backup, or None if failed
        """
        try:
            db_path = Path(db_path).resolve()
            if not db_path.exists():
                _get_logger().warning(f"Database file not found: {db_path}")
                return None

            # Check if database is empty (no tables with data)
            # If empty, no backup needed
            if self._is_database_empty(db_path):
                _get_logger().info("Database is empty, skipping backup")
                return None

            backup_dir = Path(backup_dir).resolve()
            backup_dir.mkdir(parents=True, exist_ok=True)

            backup_uuid = str(uuid.uuid4())
            timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")

            # Backup main database file
            backup_filename = f"database-{db_path.stem}-{timestamp}-{backup_uuid}.db"
            backup_path = backup_dir / backup_filename
            shutil.copy2(db_path, backup_path)

            # Backup sidecar files if they exist
            sidecar_extensions = [".wal", ".shm", ".journal"]
            sidecar_files = []
            for ext in sidecar_extensions:
                sidecar_path = db_path.with_suffix(db_path.suffix + ext)
                if sidecar_path.exists():
                    sidecar_backup = backup_dir / f"{backup_filename}{ext}"
                    shutil.copy2(sidecar_path, sidecar_backup)
                    sidecar_files.append(str(sidecar_backup.name))

            _get_logger().info(
                f"Database backup created: {backup_path} (UUID: {backup_uuid})"
            )
            return backup_uuid

        except Exception as e:
            _get_logger().error(f"Failed to create database backup: {e}", exc_info=True)
            return None

    def _is_database_empty(self, db_path: Path) -> bool:
        """
        Check if database is empty (no tables or no data).

        Args:
            db_path: Path to database file

        Returns:
            True if database is empty, False otherwise
        """
        try:
            import sqlite3

            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()

            # Check if any tables exist
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
            tables = cursor.fetchall()

            if not tables:
                conn.close()
                return True

            # Check if any table has data
            for (table_name,) in tables:
                cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                count = cursor.fetchone()[0]
                if count > 0:
                    conn.close()
                    return False

            conn.close()
            return True
        except Exception as e:
            _get_logger().warning(f"Failed to check if database is empty: {e}")
            # If we can't check, assume not empty (safer)
            return False

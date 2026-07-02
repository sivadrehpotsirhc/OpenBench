"""
services/backup_service.py
Database backup service for the Web Version.
Zips the unified database file.
"""
import os
import zipfile
from datetime import datetime, timedelta
from config import DB_PATH, DATA_DIR

BACKUP_DIR = os.path.join(DATA_DIR, "backups")

def get_backup_dir():
    from core.settings import get_setting
    custom_dir = get_setting("backup_directory", "")
    if custom_dir and os.path.exists(custom_dir) and os.path.isdir(custom_dir):
        return custom_dir
    return os.path.join(DATA_DIR, "backups")

def get_backup_info():
    from core.settings import get_setting
    
    bd = get_backup_dir()
    freq = get_setting("backup_frequency", "daily")
    retention = get_setting("backup_retention_days", "14")
    last_run = get_setting("last_backup_run", "Never")
    
    return {
        "directory": bd,
        "frequency": freq,
        "retention_days": retention,
        "last_run": last_run
    }

def run_backup():
    """Create a zipped backup of the database."""
    if not os.path.exists(DB_PATH):
        return None

    backup_dir = get_backup_dir()
    if not os.path.exists(backup_dir):
        try:
            os.makedirs(backup_dir)
        except Exception as e:
            print(f"Could not create backup directory: {e}")
            return None

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    zip_filename = os.path.join(backup_dir, f"backup_{timestamp}.zip")

    try:
        with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
            zipf.write(DB_PATH, arcname=os.path.basename(DB_PATH))
        
        _prune_backups()
        return zip_filename
    except Exception as e:
        print(f"Backup error: {e}")
        return None

def _prune_backups():
    """Remove backups older than N days."""
    from core.settings import get_setting
    try:
        days = int(get_setting("backup_retention_days", "14"))
    except ValueError:
        days = 14
        
    backup_dir = get_backup_dir()
    now = datetime.now()
    if not os.path.exists(backup_dir):
        return
        
    for filename in os.listdir(backup_dir):
        if not filename.endswith(".zip"):
            continue
        file_path = os.path.join(backup_dir, filename)
        if os.path.isfile(file_path):
            file_time = datetime.fromtimestamp(os.path.getmtime(file_path))
            if now - file_time > timedelta(days=days):
                try:
                    os.remove(file_path)
                except Exception:
                    pass

def list_backups():
    """Return a list of available backups."""
    backup_dir = get_backup_dir()
    if not os.path.exists(backup_dir):
        return []
    
    backups = []
    for filename in os.listdir(backup_dir):
        if not filename.endswith(".zip") or not filename.startswith("backup_"):
            continue
        file_path = os.path.join(backup_dir, filename)
        stat = os.stat(file_path)
        backups.append({
            "filename": filename,
            "size": stat.st_size,
            "created": datetime.fromtimestamp(stat.st_mtime).isoformat()
        })
    return sorted(backups, key=lambda x: x["created"], reverse=True)

def restore_backup(zip_path: str) -> bool:
    """Restores the database from a given zip file."""
    import shutil
    try:
        # Create a pre-restore safety backup
        run_backup()
        
        # We need to extract the zip file
        import tempfile
        with tempfile.TemporaryDirectory() as tmp_dir:
            with zipfile.ZipFile(zip_path, 'r') as zipf:
                for member in zipf.namelist():
                    member_path = os.path.realpath(os.path.join(tmp_dir, member))
                    if not member_path.startswith(os.path.realpath(tmp_dir)):
                        raise ValueError(f"Zip slip detected: {member}")
                zipf.extractall(tmp_dir)
                
            # The zip should contain exactly one file which is the database
            extracted_files = os.listdir(tmp_dir)
            db_file = None
            for f in extracted_files:
                if f.endswith('.db') or f == os.path.basename(DB_PATH):
                    db_file = os.path.join(tmp_dir, f)
                    break
                    
            if not db_file:
                return False
                
            # Replace current DB with the extracted one using SQLite's online backup API
            import sqlite3
            with sqlite3.connect(db_file) as src_conn:
                with sqlite3.connect(DB_PATH) as dest_conn:
                    src_conn.backup(dest_conn)
            
            # Reconnect all connections or trust the next request will get a fresh connection pool
            return True
    except Exception as e:
        print(f"Restore error: {e}")
        return False

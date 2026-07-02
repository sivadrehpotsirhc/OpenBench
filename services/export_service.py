import os
import csv
import json
import zipfile
import tempfile
from datetime import datetime
from core.db import get_conn

def export_all_data() -> str:
    """
    Exports all major data tables to CSVs, settings to JSON,
    bundles them into a ZIP, and returns the path to the ZIP file.
    """
    tables_to_export = [
        "tickets", "repair_log", "parts", "vendors", 
        "devices", "customers", "expenses", "transactions"
    ]
    
    tmp_dir = tempfile.mkdtemp()
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    zip_filename = os.path.join(tempfile.gettempdir(), f"30OrLess_Export_{timestamp}.zip")
    
    files_to_zip = []
    
    with get_conn() as con:
        # 1. Export tables to CSV
        for table in tables_to_export:
            try:
                # Check if table exists
                exists = con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
                if not exists:
                    continue
                    
                if table not in tables_to_export:
                    continue
                rows = con.execute(f"SELECT * FROM {table}").fetchall()
                if rows:
                    csv_path = os.path.join(tmp_dir, f"{table}.csv")
                    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                        writer = csv.writer(f)
                        # Write headers
                        writer.writerow(rows[0].keys())
                        # Write data
                        for row in rows:
                            writer.writerow(tuple(row))
                    files_to_zip.append(csv_path)
            except Exception as e:
                print(f"Error exporting table {table}: {e}")
                
        # 2. Export settings to JSON
        try:
            settings_rows = con.execute("SELECT key, value FROM settings").fetchall()
            settings_dict = {r["key"]: r["value"] for r in settings_rows}
            json_path = os.path.join(tmp_dir, "settings.json")
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(settings_dict, f, indent=4)
            files_to_zip.append(json_path)
        except Exception as e:
            print(f"Error exporting settings: {e}")
            
    # 3. Create ZIP file
    with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for file_path in files_to_zip:
            zipf.write(file_path, arcname=os.path.basename(file_path))
            
    # Clean up temp files
    for file_path in files_to_zip:
        try:
            os.remove(file_path)
        except:
            pass
    try:
        os.rmdir(tmp_dir)
    except:
        pass
        
    return zip_filename

def export_module(module_name: str) -> str:
    """
    Exports a single module to CSV and returns the path.
    """
    valid_modules = ["tickets", "parts", "vendors", "devices", "customers", "expenses"]
    if module_name not in valid_modules:
        return None
        
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    csv_filename = os.path.join(tempfile.gettempdir(), f"{module_name}_export_{timestamp}.csv")
    
    with get_conn() as con:
        try:
            exists = con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (module_name,)).fetchone()
            if not exists:
                return None
                
            if module_name not in valid_modules:
                return None
            rows = con.execute(f"SELECT * FROM {module_name}").fetchall()
            with open(csv_filename, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                if rows:
                    writer.writerow(rows[0].keys())
                    for row in rows:
                        writer.writerow(tuple(row))
            return csv_filename
        except Exception as e:
            print(f"Error exporting module {module_name}: {e}")
            return None

from core.db import get_conn
from services.backup_service import run_backup

def reset_all_data() -> bool:
    """
    Creates a backup, drops all data tables, and re-initializes them.
    Settings and PINs are also cleared, meaning the user will have to set up again.
    """
    # 1. Create safety backup
    run_backup()
    
    with get_conn() as con:
        con.execute("PRAGMA foreign_keys = OFF;")
        try:
            # Query all user table names
            cursor = con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
            tables = [row[0] for row in cursor.fetchall()]
            for table in tables:
                con.execute(f"DROP TABLE IF EXISTS {table}")
            # Reset autoincrement sequences
            con.execute("DELETE FROM sqlite_sequence")
        except Exception as e:
            print(f"Error dropping database tables: {e}")
        finally:
            con.execute("PRAGMA foreign_keys = ON;")
                
    # 2. Re-initialize the database schema
    from core.db import init_db
    from core.plugin_loader import plugin_manager
    init_db()
    plugin_manager.init_dbs()
    
    return True

def reset_module(module_name: str) -> bool:
    """
    Drops and recreates only the specific module's tables.
    """
    import os
    import json
    import shutil
    from core.plugin_loader import plugin_manager
    
    valid_modules = {
        "tickets": ["tickets", "repair_log", "ticket_photos"],
        "repair-tickets": ["tickets", "repair_log", "ticket_photos"],
        "inventory": ["parts", "vendors", "transactions"],
        "buysell": ["devices"],
        "buy-sell": ["devices"],
        "finance": ["expenses"],
        "customers": ["customers"],
        "knowledgebase": ["knowledge_bites"],
        "knowledge-base": ["knowledge_bites"]
    }
    
    is_plugin = module_name in plugin_manager.plugins
    
    if module_name not in valid_modules and not is_plugin:
        return False
        
    # Create safety backup
    run_backup()
    
    if is_plugin:
        plugin = plugin_manager.plugins[module_name]
        tables_to_drop = plugin.get("tables", [])
        
        # Fallback: check if we have predefined tables in valid_modules (for core plugins)
        if not tables_to_drop and module_name in valid_modules:
            tables_to_drop = valid_modules[module_name]
            
        # Fallback: auto-detect tables by naming convention (starting with plugin_id or plugin_id_with_underscores)
        if not tables_to_drop:
            normalized_id = module_name.replace('-', '_')
            with get_conn() as con:
                sqlite_tables = con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
                for row in sqlite_tables:
                    name = row["name"]
                    if name.startswith(module_name + "_") or name.startswith(normalized_id + "_"):
                        tables_to_drop.append(name)
    else:
        tables_to_drop = valid_modules[module_name]
    
    # Clear database tables
    if tables_to_drop:
        with get_conn() as con:
            for table in tables_to_drop:
                try:
                    # We can just DELETE FROM instead of DROP so we don't have to re-run specific CREATE TABLE schemas
                    # that might be scattered in plugin files.
                    con.execute(f"DELETE FROM {table}")
                    con.execute("DELETE FROM sqlite_sequence WHERE name=?", (table,))
                except Exception as e:
                    print(f"Error clearing table {table}: {e}")
                    
    # Re-run plugin DB initialization to restore seed data
    if is_plugin:
        plugin = plugin_manager.plugins[module_name]
        db_entry = plugin.get("entry_points", {}).get("db_init")
        if db_entry:
            plugin_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "plugins", module_name)
            py_path = os.path.join(plugin_dir, db_entry)
            if os.path.exists(py_path):
                import importlib.util
                spec = importlib.util.spec_from_file_location(f"plugin_{module_name}_db", py_path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                if hasattr(module, "init_db"):
                    module.init_db()
                else:
                    fallback_name = "_init_" + module_name.replace('-', '')
                    if hasattr(module, fallback_name):
                        getattr(module, fallback_name)()
                        
        # Clear files in tools_library if exists (or generic storage)
        plugin_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "plugins", module_name)
        library_dir = os.path.join(plugin_dir, "tools_library")
        if os.path.exists(library_dir):
            for item in os.listdir(library_dir):
                item_path = os.path.join(library_dir, item)
                try:
                    if os.path.isfile(item_path):
                        os.remove(item_path)
                    elif os.path.isdir(item_path):
                        shutil.rmtree(item_path)
                except Exception as e:
                    print(f"Error deleting storage item {item_path}: {e}")
                
    return True

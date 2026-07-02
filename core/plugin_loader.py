import os
import json
import importlib.util
from fastapi import APIRouter

PLUGIN_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "plugins")

class PluginManager:
    def __init__(self):
        self.plugins = {}
        self.routers = []
        self.db_inits = []

    def init_dbs(self):
        for init_func in self.db_inits:
            init_func()

    def load_all(self):
        if not os.path.exists(PLUGIN_DIR):
            os.makedirs(PLUGIN_DIR)
        
        for item in os.listdir(PLUGIN_DIR):
            path = os.path.join(PLUGIN_DIR, item)
            if os.path.isdir(path):
                manifest_path = os.path.join(path, "plugin.json")
                if os.path.exists(manifest_path):
                    self._load_plugin(path, manifest_path)
    
    def _load_plugin(self, path, manifest_path):
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        
        plugin_id = manifest.get("id")
        self.plugins[plugin_id] = manifest
        
        # Load DB init if exists
        db_entry = manifest.get("entry_points", {}).get("db_init")
        if db_entry:
            py_path = os.path.join(path, db_entry)
            if os.path.exists(py_path):
                spec = importlib.util.spec_from_file_location(f"plugin_{plugin_id}_db", py_path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                if hasattr(module, "init_db"):
                    self.db_inits.append(module.init_db)
                elif hasattr(module, "_init_" + plugin_id.replace('-', '')): # Fallback for old names
                    self.db_inits.append(getattr(module, "_init_" + plugin_id.replace('-', '')))
                    
        # Load backend entry point if exists
        entry = manifest.get("entry_points", {}).get("backend")
        if entry:
            py_path = os.path.join(path, entry)
            if os.path.exists(py_path):
                spec = importlib.util.spec_from_file_location(f"plugin_{plugin_id}", py_path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                
                # Check for router
                if hasattr(module, "router"):
                    prefix = manifest.get("prefix", f"/api/v1/{plugin_id}")
                    self.routers.append((prefix, module.router))

plugin_manager = PluginManager()

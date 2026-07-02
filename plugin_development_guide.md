# OpenBench Plugin Development Guide

This guide explains how to create plugins for the OpenBench IT Service Center application. The plugin system is designed to be highly modular, allowing you to add new features, API routes, database tables, and frontend UI components with minimal configuration.

## What's Handled Automatically?

When you create a plugin, the main application automatically does the heavy lifting for you:

1. **Navigation**: A tab with your plugin's name is automatically added to the top navigation bar.
2. **Frontend Injection**: The main app automatically fetches your UI components (`view.html`, `panels.html`) and injects them into the Single Page Application without any page reloads.
3. **Script Execution**: Your `module.js` file is dynamically injected into the `<head>` of the application.
4. **Backend Routing**: Your FastAPI routes are automatically mounted under `/api/v1/{plugin-id}/`.
5. **Security**: All your plugin routes are automatically protected by the main application's authentication system (`get_current_user`). No need to write auth checks manually!
6. **Database Initialization**: If your plugin needs new SQL tables, its `init_db()` function is executed at startup.

---

## Directory Structure

All plugins reside in the `plugins/` directory. A standard plugin has the following structure:

```text
plugins/
└── your_plugin_id/
    ├── plugin.json       # Required: Manifest file
    ├── db.py             # Optional: Database initialization
    ├── routes.py         # Optional: FastAPI backend routes
    └── frontend/         # Optional: Frontend UI components
        ├── view.html     # Main view interface
        ├── panels.html   # Modals and slide-over panels
        └── module.js     # Frontend logic/state
```

---

## 1. The Manifest (`plugin.json`)

Every plugin must have a `plugin.json` file in its root. This tells the system how to identify and load the plugin.

```json
{
  "id": "my-plugin",
  "name": "My Plugin",
  "version": "1.0.0",
  "entry_points": {
    "backend": "routes.py",
    "db_init": "db.py"
  }
}
```

> [!IMPORTANT]
> The `id` is crucial. It is used as your backend API prefix (`/api/v1/my-plugin`) and as the internal page identifier for the frontend tab (`page === 'my-plugin'`).

---

## 2. Backend Implementation

### Database Initialization (`db.py`)
If your plugin requires custom database tables, define an `init_db()` function in `db.py`. The application uses SQLite.

```python
from core.db import get_conn

def init_db():
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS my_plugin_data (
            id TEXT PRIMARY KEY,
            data TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
```

### API Routes (`routes.py`)
To expose backend endpoints, create an `APIRouter` named `router` in `routes.py`.

```python
from fastapi import APIRouter, HTTPException
from typing import Optional
from pydantic import BaseModel

# MUST be named `router`
router = APIRouter()

class DataPayload(BaseModel):
    data: str

# This route will automatically be available at: /api/v1/my-plugin/items
@router.get("/items")
def get_items():
    return {"status": "success", "items": []}

@router.post("/items")
def create_item(payload: DataPayload):
    return {"status": "created", "data": payload.data}
```

---

## 3. Frontend Implementation

The frontend uses **Tailwind CSS** for styling and **Alpine.js** for interactivity. Because it's a Single Page Application (SPA), your files are injected directly into the main DOM.

### `frontend/view.html`
This is your plugin's main screen. When the user clicks your plugin's tab, this HTML is shown. You do not need to include `<html>` or `<body>` tags. 

```html
<div class="plugin-view">
  <div class="section-head">
    <span class="section-title">My Plugin Dashboard</span>
    <button class="btn btn-primary" @click="panel = 'my_plugin_modal'">Open Modal</button>
  </div>

  <div class="p-6">
    <p>Welcome to my custom plugin view!</p>
  </div>
</div>
```

### `frontend/panels.html`
Use this file to define modals, forms, or slide-over panels. The main application uses a global Alpine state variable called `panel` to control what modal is open.

To show your panel, set `panel = 'my_plugin_modal'`.

```html
<div class="panel-overlay" x-show="panel === 'my_plugin_modal'" @click.self="closePanel()" x-cloak>
  <div class="panel-content w-[500px]">
    <div class="panel-head">
      <span class="panel-title">My Plugin Modal</span>
      <button class="close-btn" @click="closePanel()"></button>
    </div>
    <div class="panel-body">
      <p>This is a custom modal for my plugin!</p>
      <button class="btn btn-primary mt-4" @click="closePanel()">Close</button>
    </div>
  </div>
</div>
```

### `frontend/module.js`
This file is injected as a `<script>` tag globally. You can use it to fetch data from your API routes, define global functions, or attach Alpine.js properties to the `window`.

```javascript
// Example: Expose a global function to fetch your plugin data
window.fetchMyPluginData = async function() {
    try {
        // Automatically authenticated!
        const res = await fetch('/api/v1/my-plugin/items');
        if (res.ok) {
            const data = await res.json();
            console.log("Plugin Data:", data);
        }
    } catch (e) {
        console.error("Failed to fetch my plugin data", e);
    }
}
```

> [!TIP]  
> Because the whole application uses a single Alpine `x-data="app()"` scope, any variables or functions defined on the `window` object can be accessed directly from your `.html` files using `@click="window.fetchMyPluginData()"`.

---

## Example Workflow for a New Plugin

1. Create `plugins/my-tools/`.
2. Add `plugin.json` with `id: "my-tools"`.
3. Add `frontend/view.html` with a basic UI.
4. Restart the `start.bat` script.
5. Log into the software. You will instantly see "My Tools" in the top navigation bar, and your UI will be rendered when clicked!

## OpenBench
Lightweight, self-hostable management software for IT shops and repair centers. Built with FastAPI, SQLite, Alpine.js &amp; Tailwind CSS. Handles tickets, CRM, invoicing, inventory, accounting, and more through a modular plugin system.

---

## Architecture Overview

OpenBench is structured for maximum modularity and ease of maintenance:
* **Backend Engine**: A FastAPI REST API that integrates with SQLite for fast, transactional operations. Uses `Pydantic` for schema validation and request modeling.
* **Frontend**: A Single Page Application (SPA) served statically. It uses **Tailwind CSS** for layout styling and **Alpine.js** for simple, reactive state management and user interface bindings.
* **Dynamic Plugin System**: Features an automated plugin loader that loads and integrates custom plugins at startup. Plugins can automatically inject frontend views, declare separate database schemas, register API routes under secure, authentication-guarded endpoints, and expose dedicated modals or layout sections.

---

## Core Features

### 👤 Customer CRM
* **Auto-Discovery**: Customers are automatically registered in the system the moment a repair ticket is created for them, removing repetitive manual entry.
* **Interactive CRM Panel**: View the total amount spent, completed repair counts, and direct contact details for any customer.
* **Relationship Notes**: Maintain a rolling log of special requests, customer history, or technician notes.
* **Repair History**: Quick-jump list of all historical tickets associated with a customer.

### 📅 Google Calendar Synchronization
* **Automatic Pushing**: Sync new or updated tickets to Google Calendar with a single click.
* **Event Tracking**: Saves calendar event IDs to the ticket database, ensuring updates or status changes modify existing calendar events instead of creating duplicates.

### 📄 Invoice & PDF Generator
* **PDF Invoicing**: Generates clean, download-ready PDF invoices using the `ReportLab` engine.
* **Auto-Calculated Totals**: Integrates tax rates, custom discounts (flat rate or percentage), and line items.
* **Custom Footer Notes**: Inject standard terms of service, payment options, or business messages onto the bottom of invoices.

### ⚙️ System Settings & Business Profile
* **Business Branding**: Customize shop name, phone number, address, currency symbol, and tax labels.
* **Access Control PINs**: Role-based access control (RBAC). The system distinguishes between the **Owner** and **Technicians**. Destructive options (such as purging databases) and credential management are restricted to owners.
* **Email Templates**: Pre-configure subject lines and message bodies with dynamic tokens (e.g. `[CUSTOMER_NAME]`, `[TICKET_ID]`, `[DEVICE]`, `[STATUS]`) to quickly launch pre-filled emails in default mail clients.
* **Automated & Manual Backups**: Schedule automated database backups (Every 6h, 12h, Daily, Weekly) with a customizable retention period. Restore the entire system instantly using a ZIP archive upload.
* **Full Data Export**: Export the entire database state as a `.zip` archive or individual modules to `.csv` format.
* **Danger Zone**: Perform soft resets of individual modules or run a full factory database nuke.

---

## Plugins

OpenBench is shipped with six functional plugins that extend the system's capabilities:

### 🎫 1. Repair Tickets
The core workbench workflow tracker:
* **Lifecycle States**: Track jobs from `Open` to `In Progress`, `Awaiting Parts`, `Completed`, and `Picked Up`.
* **Mobile-Friendly QR Uploads**: Generate a secure, temporary, and unauthenticated QR code on the desktop interface. Technicians can scan it with a mobile device to open a local upload session, allowing them to snap photos of physical damage or serial numbers and upload them directly to the server without logging in on the phone.
* **Custom Ticket Options**: Customize ticket priorities, technician names, specific device classes, and common repair types.
* **Check-ins & Legal Signatures**: Configurable checklist audits (pre-repair condition) and digital legal waivers that customers sign during drop-off.
* **Status Logs**: Every single transition of status is timestamped and recorded in an audit log with notes.

### 📦 2. Inventory & Vendor Management
Keep parts stocked and track your supply chain:
* **SKU & Category Search**: Filter parts by categories, manufacturer, and shelf location.
* **Reorder Point Notifications**: Instantly flags items that fall below threshold stock quantities.
* **Vendor Directory**: Link parts to suppliers containing contact numbers, emails, websites, and notes.

### 📈 3. Finance & Expense Tracking
An financial overview dashboard for business owners:
* **Margin & Profit Math**: Automatically compiles totals from **Repair Revenue**, **Device Sales**, **Device Purchases**, and general **Expenses** to display net profit margins.
* **Expense Categorization**: Group overhead costs (e.g., Parts, Rent, Software, Utilities).
* **Exporting**: Dump financial ledger entries directly into standard CSV format.

### 📱 4. Buy & Sell Devices
Tracks retail and trade-in operations:
* **Condition Grading**: Log device condition (New, Mint, Good, Fair, Poor).
* **Status Pipelines**: Track devices through `Staging` (refurbishing), `Ready` (listed for sale), and `Sold`.
* **Margin Analysis**: Compare purchase prices against actual sale prices to optimize resale returns.

### 🧠 5. Knowledge Base
A repository of repair knowledge and solutions for common device issues:
* **Automated Syncing**: Automatically imports completed repair tickets, transforming diagnosed issues and solutions into searchable knowledge bites.
* **Global Search**: Instantly query historical fixes and procedures by device name, problem descriptions, or solution keywords.
* **Manual Entries**: Add, update, and manage custom tips, notes, and fixes directly.

### 💾 6. Software Repository *(Optional)*
An IT-centric utility hosting and deployment portal:
* **Tool Library**: Upload, organize, and categorize portable diagnostic tools, software utilities, and scripts.
* **Temporary Guest Portal**: Generate a secure, temporary, 6-digit session PIN to access a client-facing download interface on repair machines without logging in with technician credentials.
* **Download Audit Logs**: Tracks client download history, timestamps, and IP addresses.
* **How to Remove**: Because this plugin is highly IT-centric and may not be needed for general repair shops, it is completely optional. If not needed, users can simply delete the [software_repo] folder located inside of your plugins folder. :)

---

## Getting Started

### 📋 Prerequisites
* Python 3.8 or higher.
* Python added to your system's `PATH`.

### 🚀 Windows Installation & Setup
1. Clone or download the OpenBench source files.
2. Run the installer:
   ```cmd
   Double-click OpenBenchSetup.bat
   ```
   *This script verifies your Python installation, updates pip, and installs all python dependencies listed in `requirements.txt`.*

3. Start the application:
   ```cmd
   Double-click start.bat
   ```
   *This launches Uvicorn on http://localhost:8000.*

4. On first launch, the login screen will prompt you to set a **6-digit Owner PIN** and type your name.

---

## Helper Scripts

* **`start.bat`**: A quick-launch script that starts the web application locally.
* **`reset_pin.py`**: If you lose access or need to reset the access credentials, run this script (`python reset_pin.py`). It clears the SQLite `pins` table, allowing you to establish a new Owner PIN upon the next page reload.

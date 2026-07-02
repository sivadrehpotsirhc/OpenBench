window.knowledgeBasePlugin = function() {
    return {
        entries: [],
        search: '',
        panelOpen: false,
        panelMode: 'new', // 'new' | 'edit'
        isSyncing: false,
        form: {
            id: null,
            device: '',
            problem: '',
            solution: ''
        },
        async init() {
            await this.fetchEntries();
        },
        showToast(message, type = 'success') {
            const rootEl = document.body;
            if (rootEl && rootEl.__x && rootEl.__x.$data && typeof rootEl.__x.$data.showToast === 'function') {
                rootEl.__x.$data.showToast(message, type);
            } else if (window.Alpine) {
                try {
                    const app = window.Alpine.$data(rootEl);
                    if (app && typeof app.showToast === 'function') {
                        app.showToast(message, type);
                        return;
                    }
                } catch(e) {}
            }
            console.log(`Toast (${type}): ${message}`);
        },
        async fetchEntries() {
            try {
                const ts = Date.now();
                const url = this.search 
                    ? `/api/v1/knowledge-base/?search=${encodeURIComponent(this.search)}&t=${ts}` 
                    : `/api/v1/knowledge-base/?t=${ts}`;
                const res = await fetch(url);
                if (res.ok) {
                    this.entries = await res.json();
                }
            } catch(e) {
                console.error("Failed to fetch knowledge base entries", e);
            }
        },
        openNew() {
            this.panelMode = 'new';
            this.form = { id: null, device: '', problem: '', solution: '' };
            this.panelOpen = true;
        },
        openEdit(entry) {
            this.panelMode = 'edit';
            this.form = { 
                id: entry.id, 
                device: entry.device, 
                problem: entry.problem, 
                solution: entry.solution 
            };
            this.panelOpen = true;
        },
        closePanel() {
            this.panelOpen = false;
        },
        async submitForm() {
            if (!this.form.device || !this.form.problem || !this.form.solution) {
                this.showToast("Please fill out all required fields", "error");
                return;
            }
            try {
                const method = this.panelMode === 'new' ? 'POST' : 'PUT';
                const url = this.panelMode === 'new' 
                    ? '/api/v1/knowledge-base/' 
                    : `/api/v1/knowledge-base/${this.form.id}`;
                
                const res = await fetch(url, {
                    method: method,
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(this.form)
                });
                if (res.ok) {
                    this.closePanel();
                    this.showToast(this.panelMode === 'new' ? "Knowledge bite added!" : "Knowledge bite updated!", "success");
                    await this.fetchEntries();
                } else {
                    this.showToast("Failed to save entry", "error");
                }
            } catch(e) {
                console.error("Error saving knowledge bite", e);
            }
        },
        async deleteEntry() {
            if (!confirm(`Are you sure you want to delete knowledge bite #${this.form.id}?`)) return;
            try {
                const res = await fetch(`/api/v1/knowledge-base/${this.form.id}`, {
                    method: 'DELETE'
                });
                if (res.ok) {
                    this.closePanel();
                    this.showToast("Knowledge bite deleted", "success");
                    await this.fetchEntries();
                } else {
                    this.showToast(`Failed to delete entry: Server returned status ${res.status}`, "error");
                }
            } catch(e) {
                console.error("Error deleting knowledge bite", e);
                this.showToast(`Error: ${e.message || e}`, "error");
            }
        },
        async syncNow() {
            if (this.isSyncing) return;
            this.isSyncing = true;
            try {
                const res = await fetch('/api/v1/knowledge-base/sync', {
                    method: 'POST'
                });
                if (res.ok) {
                    const data = await res.json();
                    const count = data.synced || 0;
                    this.showToast(`Synced ${count} new completed tickets!`, "success");
                    await this.fetchEntries();
                } else {
                    this.showToast("Failed to sync completed tickets", "error");
                }
            } catch(e) {
                console.error("Error syncing completed tickets", e);
                this.showToast("Error during sync operation", "error");
            } finally {
                this.isSyncing = false;
            }
        }
    };
};

window.softwareRepoPlugin = function() {
    return {
        tools: [],
        categories: [],
        sessions: [],
        downloads: [],
        search: '',
        activeTab: 'tools', // 'tools' | 'sessions' | 'downloads'
        panelOpen: false,
        panelMode: '', // 'add_tool' | 'show_pin'
        isUploading: false,
        isGenerating: false,
        ttlMinutes: 60,
        generatedPin: null, // { token, pin, expires_at, ttl_minutes }
        newTool: {
            name: '',
            description: '',
            version: '',
            category_id: '',
            is_portable: true,
            file: null
        },

        async init() {
            await this.fetchCategories();
            await this.fetchTools();
            await this.fetchSessions();
            await this.fetchDownloads();
        },

        getCategoryOptionsHtml() {
            return this.categories.map(c => `<option value="${c.id}">${c.name}</option>`).join('');
        },

        async fetchTools() {
            try {
                const res = await fetch(`/app/tools/tools?_t=${Date.now()}`);
                if (res.ok) {
                    this.tools = await res.json();
                }
            } catch (e) {
                console.error("Failed to fetch tools", e);
            }
        },

        async fetchCategories() {
            try {
                const res = await fetch(`/app/tools/categories?_t=${Date.now()}`);
                if (res.ok) {
                    this.categories = await res.json();
                    if (this.categories.length > 0) {
                        this.newTool.category_id = this.categories[0].id;
                    }
                }
            } catch (e) {
                console.error("Failed to fetch categories", e);
            }
        },

        async fetchSessions() {
            try {
                const res = await fetch(`/app/tools/sessions?_t=${Date.now()}`);
                if (res.ok) {
                    this.sessions = await res.json();
                }
            } catch (e) {
                console.error("Failed to fetch sessions", e);
            }
        },

        async fetchDownloads() {
            try {
                const res = await fetch(`/app/tools/downloads?_t=${Date.now()}`);
                if (res.ok) {
                    this.downloads = await res.json();
                }
            } catch (e) {
                console.error("Failed to fetch downloads", e);
            }
        },

        filteredTools() {
            if (!this.search) return this.tools;
            const q = this.search.toLowerCase();
            return this.tools.filter(t => 
                t.name.toLowerCase().includes(q) || 
                (t.description && t.description.toLowerCase().includes(q)) ||
                (t.category_name && t.category_name.toLowerCase().includes(q))
            );
        },

        openAddTool() {
            this.panelMode = 'add_tool';
            this.newTool = {
                name: '',
                description: '',
                version: '',
                category_id: this.categories.length > 0 ? this.categories[0].id : '',
                is_portable: true,
                file: null
            };
            // Clear file input manually in DOM if exists
            const fileInput = document.getElementById('tool-file-input');
            if (fileInput) fileInput.value = '';
            this.panelOpen = true;
        },

        handleFileChange(event) {
            const file = event.target.files[0];
            if (file) {
                this.newTool.file = file;
                if (!this.newTool.name) {
                    // Pre-fill name from file name (sans extension)
                    const baseName = file.name.substring(0, file.name.lastIndexOf('.')) || file.name;
                    this.newTool.name = baseName.replace(/[-_]/g, ' ');
                }
            }
        },

        async submitToolForm() {
            // Retrieve value directly from select element to prevent any x-model synchronization delay with dynamic elements
            const selectEl = document.getElementById('tool-category-select');
            if (selectEl && selectEl.value) {
                this.newTool.category_id = selectEl.value;
            }
            if (!this.newTool.category_id && this.categories.length > 0) {
                this.newTool.category_id = this.categories[0].id;
            }

            if (!this.newTool.name || !this.newTool.category_id || !this.newTool.file) {
                this.toast("Name, Category, and File are required", "error");
                return;
            }

            this.isUploading = true;
            const formData = new FormData();
            formData.append('name', this.newTool.name);
            formData.append('description', this.newTool.description || '');
            formData.append('version', this.newTool.version || '1.0');
            formData.append('category_id', this.newTool.category_id);
            formData.append('is_portable', this.newTool.is_portable ? 'true' : 'false');
            formData.append('file', this.newTool.file);

            try {
                const res = await fetch('/app/tools/tools/add', {
                    method: 'POST',
                    body: formData
                });
                if (res.ok) {
                    this.closePanel();
                    this.toast("Tool uploaded successfully!", "success");
                    await this.fetchTools();
                } else {
                    const err = await res.json();
                    this.toast(err.detail || "Upload failed", "error");
                }
            } catch (e) {
                console.error("Error uploading tool", e);
                this.toast("Network error during upload", "error");
            } finally {
                this.isUploading = false;
            }
        },

        async toggleTool(tool) {
            try {
                const res = await fetch(`/app/tools/tools/${tool.id}/toggle`, {
                    method: 'POST'
                });
                if (res.ok) {
                    const data = await res.json();
                    tool.is_active = data.is_active;
                    this.toast(tool.is_active ? "Tool enabled" : "Tool disabled", "success");
                } else {
                    this.toast("Failed to toggle tool", "error");
                }
            } catch (e) {
                console.error("Error toggling tool", e);
            }
        },

        async deleteTool(tool) {
            if (!confirm(`Are you sure you want to delete "${tool.name}"? This will delete the file from the server.`)) return;
            try {
                const res = await fetch(`/app/tools/tools/${tool.id}`, {
                    method: 'DELETE'
                });
                if (res.ok) {
                    this.toast("Tool deleted", "success");
                    await this.fetchTools();
                } else {
                    this.toast("Failed to delete tool", "error");
                }
            } catch (e) {
                console.error("Error deleting tool", e);
            }
        },

        async generatePin() {
            this.isGenerating = true;
            try {
                const res = await fetch('/app/tools/sessions/create', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ ttl_minutes: parseInt(this.ttlMinutes) })
                });
                if (res.ok) {
                    this.generatedPin = await res.json();
                    this.panelMode = 'show_pin';
                    this.panelOpen = true;
                    await this.fetchSessions();
                } else {
                    this.toast("Failed to generate PIN", "error");
                }
            } catch (e) {
                console.error("Error generating PIN", e);
                this.toast("Error generating session", "error");
            } finally {
                this.isGenerating = false;
            }
        },

        async revokeSession(session) {
            if (!confirm("Are you sure you want to revoke this session? The guest will be disconnected immediately.")) return;
            try {
                const res = await fetch(`/app/tools/sessions/${session.id}/revoke`, {
                    method: 'POST'
                });
                if (res.ok) {
                    this.toast("Session revoked", "success");
                    await this.fetchSessions();
                } else {
                    this.toast("Failed to revoke session", "error");
                }
            } catch (e) {
                console.error("Error revoking session", e);
            }
        },

        closePanel() {
            this.panelOpen = false;
            this.panelMode = '';
        },

        toast(message, type = "success") {
            // Check if Alpine 3 global exists and can access the body state
            if (window.Alpine) {
                try {
                    const appData = window.Alpine.$data(document.body);
                    if (appData && typeof appData.showToast === 'function') {
                        appData.showToast(message, type);
                        return;
                    }
                } catch (e) {
                    console.error("Error accessing Alpine app data", e);
                }
            }
            // Fallback: search DOM for the main app container and use its Alpine state
            const rootEl = document.querySelector('body');
            if (rootEl && rootEl.__x && rootEl.__x.$data && typeof rootEl.__x.$data.showToast === 'function') {
                rootEl.__x.$data.showToast(message, type);
                return;
            }
            alert(message);
        },

        formatSize(kb) {
            if (kb >= 1024) return (kb / 1024).toFixed(2) + " MB";
            return kb + " KB";
        },

        formatDate(dateStr) {
            if (!dateStr) return "—";
            try {
                const d = new Date(dateStr + " UTC"); // Ensure parsed as UTC
                return d.toLocaleString();
            } catch (e) {
                return dateStr;
            }
        }
    };
};

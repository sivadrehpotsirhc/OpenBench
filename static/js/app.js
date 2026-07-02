
    function addBizDays(n) {
      if (!n) return null
      let d = new Date(), count = 0
      while (count < n) {
        d.setDate(d.getDate() + 1)
        if (d.getDay() !== 0 && d.getDay() !== 6) count++
      }
      return d.toLocaleDateString('en-US', { weekday:'short', month:'short', day:'2-digit', year:'numeric' })
    }

    function app() {
      return {
        pluginViews: [],
        pluginPanels: [],
        isOffline: false,
        page: 'home',
        panel: null,   // 'ticket' | 'new' | null
        
        getGreeting() {
          const name = this.auth.user?.name || 'User';
          const hour = new Date().getHours();
          if (hour >= 6 && hour < 12) {
            return `Good Morning ${name}!`;
          } else if (hour >= 12 && hour < 18) {
            return `Good Afternoon ${name}!`;
          } else if (hour >= 18 && hour < 24) {
            return `Good Evening ${name}`;
          } else {
            return `It's a little late isn't it ${name}?`;
          }
        },
        settingsTab: 'profile',
        currentTime: '',
        config: {},
        emailTemplates: [],
        pinsList: [],
        showAddPin: false,
        newPin: { label: '', role: 'technician', pin: '' },
        systemInfo: null,
        backupInfo: null,
        dangerModule: '',
        dangerModuleConfirm: '',
        dangerAllConfirm: '',

        // Data
        tickets:   [],
        stats:     {},
        customers: [],
        invStats:  {},
        bsStats:   {},
        inventoryParts:   [],
        inventoryVendors: [],

        // Filters
        ticketSearch:   '',
        ticketStatus:   '',
        ticketPriority: '',
        ticketSortBy:   '',
        ticketSortDesc: false,
        custSearch:     '',
        inventorySearch: '',
        inventoryLowStock: false,
        inventorySortBy:   '',
        inventorySortDesc: false,
        bsSearch:       '',
        bsStatus:       '',
        bsDeviceSortBy:    '',
        bsDeviceSortDesc:  false,

        // Active ticket
        activeTicket: null,
        activePart:   null,
        activeDevice: null,
        panelMode:    'view',  // 'view' | 'edit' | 'log'
        editForm:     {},
        partForm:     {},
        bsForm:       {},
        repairLog:    [],
        logEntry:     { status: 'In Progress', note: '' },
        ticketPhotos: [],
        photoDropdownOpen: false,
        qrSession: null,
        qrModalOpen: false,
        pollTimer: null,
        customerQuery: '',
        customerSuggestions: [],
        selectedSuggestionIndex: -1,

        // New ticket form
        submitting: false,
        repairHint: '',
        form: {
          priority:'Standard', name:'', phone:'', email:'',
          address:'', device:'', serial:'', repair:'',
          price:'', issue:'', notes:'',
          technician:'', due:'',
          tax_exempt: false,
          discount_type: 'None',
          custom_data: '{}',
          pre_repair_json: '{}',
          legal_json: '{}'
        },

        // Toast
        toastMsg: '', toastType: 'success', toastVisible: false, _toastTimer: null,

        plugins: [],
        // '#3b82f6' was the pre-Foundry default; treat it as unset so old clients pick up ember
        accentColor: (localStorage.getItem('ob-accent') === '#3b82f6' ? null : localStorage.getItem('ob-accent')) || '#f97316',
        auth: {
          isAuthenticated: false,
          hasPin: true,
          pinInput: '',
          error: '',
          user: null,
          setupLabel: ''
        },

        async checkAuth() {
          try {
            const res = await fetch('/api/settings/auth/status');
            if (res.ok) {
              this.isOffline = false;
              const data = await res.json();
              this.auth.isAuthenticated = data.is_authed;
              this.auth.hasPin = data.has_pin;
              this.auth.user = data.user;
              this.auth.shopName = data.shop_name;
              if (this.auth.isAuthenticated) {
                this.loadApp();
              }
            } else {
              this.isOffline = true;
            }
          } catch (e) {
            console.error('Auth check failed', e);
            this.isOffline = true;
          }
        },

        async submitPin() {
          if (!this.auth.pinInput) return;
          try {
            const res = await fetch('/api/settings/auth/login', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ pin: this.auth.pinInput, label: this.auth.setupLabel })
            });
            if (res.ok) {
              this.isOffline = false;
              const data = await res.json();
              this.auth.isAuthenticated = true;
              this.auth.user = data.user;
              this.auth.error = '';
              this.loadApp();
            } else {
              const err = await res.json();
              this.auth.error = err.error || 'Invalid PIN';
              this.auth.pinInput = '';
            }
          } catch(e) {
            this.auth.error = 'Login failed';
            this.isOffline = true;
          }
        },

        async loadApp() {
          if (this._appLoaded) return;
          this._appLoaded = true;
          await this.fetchConfig()
          await this.fetchPlugins()
          await this.fetchConstants()
          await this.fetchTickets()
          await this.fetchStats()
          
          // Fetch plugin data
          if (this.fetchInventoryStats) this.fetchInventoryStats()
          if (this.fetchBuySellStats)   this.fetchBuySellStats()
          if (this.fetchFinanceSummary) this.fetchFinanceSummary()
          if (this.fetchCustomers)      this.fetchCustomers()
          
          this.setupHotkeys()
          this.startClock()
        },


        applyAccentColor() {
          const root = document.documentElement.style;
          if (this.accentColor === '#f97316') {
            // default ember: let the stylesheet's 400/500/600 shades apply
            root.removeProperty('--accent');
            root.removeProperty('--accent-hot');
            root.removeProperty('--accent-deep');
          } else {
            root.setProperty('--accent', this.accentColor);
            root.setProperty('--accent-hot', this.accentColor);
            root.setProperty('--accent-deep', this.accentColor);
          }
          localStorage.setItem('ob-accent', this.accentColor);
        },
        panelsHtml: '',

        // Constants (fetched from API)
        STATUSES: [],
        DEVICES:  [],
        REPAIRS:  [],
        CATEGORIES: [],
        REPAIR_PRICE: {},
        REPAIR_DAYS: {},
        TICKET_MODULES: [],
        TICKET_TECHS: [],
        TICKET_CHECKLIST: [],
        TICKET_LEGAL: [],


        async init() {
          this.applyAccentColor();
          this.$watch('dangerModule', value => {
            this.dangerModuleConfirm = '';
          });
          this.$watch('pluginViews', () => {
            this.$nextTick(() => {
              const el = document.getElementById('plugin-views');
              if (el && window.Alpine && typeof window.Alpine.initTree === 'function') {
                window.Alpine.initTree(el);
              }
            });
          });
          this.$watch('pluginPanels', () => {
            this.$nextTick(() => {
              const el = document.getElementById('plugin-panels');
              if (el && window.Alpine && typeof window.Alpine.initTree === 'function') {
                window.Alpine.initTree(el);
              }
            });
          });
          await this.checkAuth();
        },


        
        async fetchPlugins() {
          try {
            this.pluginViews = [];
            this.pluginPanels = [];
            const res = await fetch('/api/settings/plugins?t=' + Date.now())
            if (res.ok) {
              this.isOffline = false;
              const list = await res.json()
              for (const p of list) {
                const folder = p.id.replace(/-/g, '_');
                const cb = '?v=' + Date.now();
                // Fetch module js first and await loading
                try {
                  await new Promise((resolve) => {
                    const script = document.createElement('script');
                    script.src = `/plugins/${folder}/frontend/module.js` + cb;
                    script.onload = () => resolve();
                    script.onerror = () => resolve();
                    document.head.appendChild(script);
                  });
                } catch(e) {}

                // Fetch view html
                try {
                  const vr = await fetch(`/plugins/${folder}/frontend/view.html` + cb)
                  if (vr.ok) {
                    this.pluginViews = [...this.pluginViews, { id: p.id, html: await vr.text() }];
                  }
                } catch(e) {}
                
                // Fetch panel html
                try {
                  const pr = await fetch(`/plugins/${folder}/frontend/panels.html` + cb)
                  if (pr.ok) {
                    this.pluginPanels = [...this.pluginPanels, await pr.text()];
                  }
                } catch(e) {}
              }
              this.plugins = list
            } else {
              this.isOffline = true;
            }
          } catch(e) {
            console.error('Failed to fetch plugins:', e);
            this.isOffline = true;
          }
        },

        async fetchConstants() {
          try {
            const r = await fetch('/api/settings/constants')
            if (r.ok) {
              this.isOffline = false;
              const data = await r.json()
              this.STATUSES = data.STATUSES || []
              this.CATEGORIES = data.PART_CATEGORIES || []
            } else {
              this.isOffline = true;
            }
          } catch(e) {
            console.error('Error fetching constants:', e);
            this.isOffline = true;
          }
          try {
            const r2 = await fetch('/api/v1/repair-tickets/plugin_settings?t=' + Date.now())
            if (r2.ok) {
              this.isOffline = false;
              const pData = await r2.json()
              this.TICKET_MODULES = pData.ticket_modules || []
              this.TICKET_TECHS = pData.ticket_techs || []
              this.TICKET_CHECKLIST = pData.ticket_checklist || []
              this.TICKET_LEGAL = pData.ticket_legal || []
              this.DEVICES = pData.ticket_devices || []
              this.REPAIRS = (pData.ticket_repair_types || []).map(r => r.name)
              this.REPAIR_PRICE = {}
              this.REPAIR_DAYS = {}
              ;(pData.ticket_repair_types || []).forEach(r => {
                this.REPAIR_PRICE[r.name] = r.price
                this.REPAIR_DAYS[r.name] = r.days
              })
            } else {
              this.isOffline = true;
            }
          } catch(e) {
            console.error('Error fetching plugin settings:', e);
            this.isOffline = true;
          }
        },

        setupHotkeys() {
          window.addEventListener('keydown', (e) => {
            // Esc: Close any open panel
            if (e.key === 'Escape') {
              if (this.panel) this.closePanel()
            }
            // Ctrl+N: New Ticket (prevent default to avoid browser new window)
            if (e.ctrlKey && e.key === 'n') {
              e.preventDefault()
              this.openNewTicket()
            }
          })
        },

        addRepairType() {
          const name = "New Repair Type " + Date.now().toString().slice(-4)
          this.REPAIRS.push(name)
          this.REPAIR_PRICE[name] = 0
          this.REPAIR_DAYS[name] = 1
          this.saveRepairSettings()
        },
        removeRepairType(name) {
          this.REPAIRS = this.REPAIRS.filter(r => r !== name)
          delete this.REPAIR_PRICE[name]
          delete this.REPAIR_DAYS[name]
          this.saveRepairSettings()
        },
        async saveRepairSettings() {
          try {
            const ticket_repair_types = this.REPAIRS.map(name => {
              const cleanVal = (this.REPAIR_PRICE[name] !== undefined && this.REPAIR_PRICE[name] !== null) ? this.REPAIR_PRICE[name].toString().replace(/[^0-9.]/g, '') : '0';
              const parsedVal = parseFloat(cleanVal);
              return {
                name: name,
                price: isNaN(parsedVal) ? 0 : parsedVal,
                days: parseInt(this.REPAIR_DAYS[name] || 0)
              };
            })
            
            const payload = {
              ticket_modules: JSON.stringify(this.TICKET_MODULES),
              ticket_repair_types: JSON.stringify(ticket_repair_types),
              ticket_devices: JSON.stringify(this.DEVICES.filter(d => d.trim() !== '')),
              ticket_techs: JSON.stringify(this.TICKET_TECHS.filter(t => t.trim() !== '')),
              ticket_checklist: JSON.stringify(this.TICKET_CHECKLIST.filter(c => c.trim() !== '')),
              ticket_legal: JSON.stringify(this.TICKET_LEGAL.filter(l => l.trim() !== ''))
            }

            const res = await fetch('/api/v1/repair-tickets/plugin_settings', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(payload)
            })
            if (res.ok) {
              this.showToast('Settings saved')
            } else {
              this.showToast('Failed to save settings', 'error')
            }
          } catch(e) {
            console.error(e)
            this.showToast('Error saving settings', 'error')
          }
        },

        async exportTickets() {
          try {
            window.location.href = '/api/v1/repair-tickets/export'
            this.showToast('Exporting tickets...', 'info')
          } catch(e) { this.showToast('Export failed', 'error') }
        },



        // ── Tickets ───────────────────────────────────────────────────────────
        async fetchTickets() {
          try {
            const p = new URLSearchParams()
            if (this.ticketSearch)   p.set('search', this.ticketSearch)
            if (this.ticketStatus)   p.set('status', this.ticketStatus)
            const res = await fetch(`/api/v1/repair-tickets/?${p}`)
            if (res.ok) {
              this.isOffline = false;
              let data = await res.json()
              if (this.ticketPriority) data = data.filter(t => t.priority === this.ticketPriority)
              this.tickets = data
              this.sortTickets()
            } else {
              this.isOffline = true;
            }
          } catch(e) {
            console.error('Error fetching tickets:', e);
            this.isOffline = true;
          }
        },

        sortTickets() {
          if (!this.ticketSortBy) return;

          const field = this.ticketSortBy;
          const desc = this.ticketSortDesc;

          this.tickets.sort((a, b) => {
            const valA = a[field];
            const valB = b[field];

            // 1. Generic sentinel/empty checks (push empty values to the bottom)
            const isAEmpty = valA === undefined || valA === null || valA === '' || valA === '—';
            const isBEmpty = valB === undefined || valB === null || valB === '' || valB === '—';

            if (isAEmpty && isBEmpty) return 0;
            if (isAEmpty) return 1;  // empty always at bottom
            if (isBEmpty) return -1; // empty always at bottom

            let res = 0;

            // 2. Column-specific sorting comparators
            if (field === 'priority') {
              const priorityOrder = ['Standard', 'Rush', 'Critical'];
              const idxA = priorityOrder.indexOf(valA);
              const idxB = priorityOrder.indexOf(valB);
              res = idxA - idxB;
            } else if (field === 'status') {
              const statusOrder = ['Open', 'In Progress', 'Waiting on Parts', 'Ready for Pickup', 'Completed', 'Cancelled'];
              const idxA = statusOrder.indexOf(valA);
              const idxB = statusOrder.indexOf(valB);
              res = idxA - idxB;
            } else if (field === 'due') {
              const dateA = new Date(Date.parse(valA));
              const dateB = new Date(Date.parse(valB));
              res = dateA - dateB;
            } else if (field === 'price') {
              const parsePrice = (str) => {
                const clean = str.toString().replace(/[^0-9.]/g, '');
                const parsed = parseFloat(clean);
                return isNaN(parsed) ? 0 : parsed;
              };
              res = parsePrice(valA) - parsePrice(valB);
            } else {
              // Default alphabetical for string fields
              res = valA.toString().localeCompare(valB.toString());
            }

            return desc ? -res : res;
          });
        },

        toggleTicketSort(field) {
          if (this.ticketSortBy === field) {
            this.ticketSortDesc = !this.ticketSortDesc;
          } else {
            this.ticketSortBy = field;
            this.ticketSortDesc = false;
          }
          this.sortTickets();
        },

        sortParts() {
          if (!this.inventorySortBy) return;

          const field = this.inventorySortBy;
          const desc = this.inventorySortDesc;

          this.inventoryParts.sort((a, b) => {
            let valA = a[field];
            let valB = b[field];

            if (field === 'vendor_name') {
              valA = a.vendor_name || '';
              valB = b.vendor_name || '';
            }

            // Generic sentinel/empty checks (push empty values to the bottom)
            const isAEmpty = valA === undefined || valA === null || valA === '' || valA === '—';
            const isBEmpty = valB === undefined || valB === null || valB === '' || valB === '—';

            if (isAEmpty && isBEmpty) return 0;
            if (isAEmpty) return 1;
            if (isBEmpty) return -1;

            let res = 0;

            // Column-specific sorting comparators
            if (field === 'qty' || field === 'reorder_point') {
              res = parseInt(valA, 10) - parseInt(valB, 10);
            } else if (field === 'cost' || field === 'sell_price') {
              res = parseFloat(valA) - parseFloat(valB);
            } else {
              res = valA.toString().localeCompare(valB.toString(), undefined, { sensitivity: 'base' });
            }

            return desc ? -res : res;
          });
        },

        toggleInventorySort(field) {
          if (this.inventorySortBy === field) {
            this.inventorySortDesc = !this.inventorySortDesc;
          } else {
            this.inventorySortBy = field;
            this.inventorySortDesc = false;
          }
          this.sortParts();
        },

        sortBSDevices() {
          if (!this.bsDeviceSortBy) return;

          const field = this.bsDeviceSortBy;
          const desc = this.bsDeviceSortDesc;

          this.bsDevices.sort((a, b) => {
            let valA = a[field];
            let valB = b[field];

            // Generic sentinel/empty checks (push empty values to the bottom)
            const isAEmpty = valA === undefined || valA === null || valA === '' || valA === '—';
            const isBEmpty = valB === undefined || valB === null || valB === '' || valB === '—';

            if (isAEmpty && isBEmpty) return 0;
            if (isAEmpty) return 1;  // empty always at bottom
            if (isBEmpty) return -1; // empty always at bottom

            let res = 0;

            // Column-specific sorting comparators
            if (field === 'customer') {
              const nameA = a.customer_name || '';
              const nameB = b.customer_name || '';
              res = nameA.localeCompare(nameB, undefined, { sensitivity: 'base' });
              if (res === 0) {
                const phoneA = a.customer_phone || '';
                const phoneB = b.customer_phone || '';
                res = phoneA.localeCompare(phoneB);
              }
            } else if (field === 'condition') {
              const conditionOrder = ['New', 'Excellent', 'Good', 'Fair', 'Poor / Parts'];
              const idxA = conditionOrder.indexOf(valA);
              const idxB = conditionOrder.indexOf(valB);
              res = idxA - idxB;
            } else if (field === 'status') {
              const statusOrder = ['Staging', 'Ready for Sale', 'Sold'];
              const idxA = statusOrder.indexOf(valA);
              const idxB = statusOrder.indexOf(valB);
              res = idxA - idxB;
            } else if (field === 'purchase_price' || field === 'sell_price') {
              res = parseFloat(valA) - parseFloat(valB);
            } else if (field === 'date_sold') {
              const dateA = new Date(Date.parse(valA));
              const dateB = new Date(Date.parse(valB));
              res = dateA - dateB;
            } else {
              res = valA.toString().localeCompare(valB.toString(), undefined, { sensitivity: 'base' });
            }

            return desc ? -res : res;
          });
        },

        toggleBSDeviceSort(field) {
          if (this.bsDeviceSortBy === field) {
            this.bsDeviceSortDesc = !this.bsDeviceSortDesc;
          } else {
            this.bsDeviceSortBy = field;
            this.bsDeviceSortDesc = false;
          }
          this.sortBSDevices();
        },



        async fetchStats() {
          try {
            const res = await fetch('/api/v1/repair-tickets/stats')
            if (res.ok) {
              this.isOffline = false;
              this.stats = await res.json()
            } else {
              this.isOffline = true;
            }
          } catch(e) {
            console.error('Error fetching stats:', e);
            this.isOffline = true;
          }
        },

        async fetchInventoryStats() {
          try {
            const res = await fetch('/api/v1/inventory/stats')
            if (res.ok) {
              this.isOffline = false;
              this.invStats = await res.json()
              await this.fetchParts()
              await this.fetchVendors()
            } else {
              this.isOffline = true;
            }
          } catch(e) {
            console.error('Error fetching inventory stats:', e);
            this.isOffline = true;
          }
        },

        async fetchParts() {
          try {
            const p = new URLSearchParams()
            if (this.inventorySearch) p.set('search', this.inventorySearch)
            if (this.inventoryLowStock) p.set('low_stock', 'true')
            const res = await fetch(`/api/v1/inventory/parts?${p}`)
            if (res.ok) {
              this.isOffline = false;
              this.inventoryParts = await res.json()
              this.sortParts()
            } else {
              this.isOffline = true;
            }
          } catch(e) {
            console.error('Error fetching parts:', e);
            this.isOffline = true;
          }
        },

        async fetchVendors() {
          try {
            const res = await fetch('/api/v1/inventory/vendors')
            if (res.ok) {
              this.isOffline = false;
              this.inventoryVendors = await res.json()
            } else {
              this.isOffline = true;
            }
          } catch(e) {
            console.error('Error fetching vendors:', e);
            this.isOffline = true;
          }
        },

        async fetchBuySellStats() {
          try {
            const res = await fetch('/api/v1/buy-sell/stats')
            if (res.ok) {
              this.isOffline = false;
              this.bsStats = await res.json()
              await this.fetchDevices()
            } else {
              this.isOffline = true;
            }
          } catch(e) {
            console.error('Error fetching buy-sell stats:', e);
            this.isOffline = true;
          }
        },

        async fetchDevices() {
          try {
            const p = new URLSearchParams()
            if (this.bsSearch) p.set('search', this.bsSearch)
            if (this.bsStatus) p.set('status', this.bsStatus)
            const res = await fetch(`/api/v1/buy-sell/?${p}`)
            if (res.ok) {
              this.isOffline = false;
              this.bsDevices = await res.json()
              this.sortBSDevices()
            } else {
              this.isOffline = true;
            }
          } catch(e) {
            console.error('Error fetching devices:', e);
            this.isOffline = true;
          }
        },

        async fetchCustomers() {
          try {
            const p = new URLSearchParams()
            if (this.custSearch) p.set('search', this.custSearch)
            const res = await fetch(`/api/customers/?${p}`)
            if (res.ok) {
              this.isOffline = false;
              this.customers = await res.json()
            } else {
              this.isOffline = true;
            }
          } catch(e) {
            console.error('Error fetching customers:', e);
            this.isOffline = true;
          }
        },

        // ── Inventory ─────────────────────────────────────────────────────────
        openNewPart() {
          this.resetPartForm()
          this.panel = 'part'
          this.panelMode = 'new'
        },

        resetPartForm() {
          this.partForm = {
            name: '', sku: '', category: 'Other', qty: 0, reorder_point: 1,
            cost: '', sell_price: '', vendor_id: '', location: '', notes: ''
          }
        },

        cleanPartData(data) {
          const d = { ...data }
          for (const key of ['cost', 'sell_price', 'vendor_id']) {
            if (d[key] === '') d[key] = null
          }
          return d
        },

        async submitPart() {
          if (!this.partForm.name) {
            this.showToast('Part name is required.', 'error')
            return
          }
          try {
            const res = await fetch('/api/v1/inventory/parts', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(this.cleanPartData(this.partForm)),
            })
            if (!res.ok) throw new Error('Failed to create part')
            this.showToast('Part added.', 'success')
            this.closePanel()
            await this.fetchInventoryStats()
          } catch(e) { this.showToast(e.message, 'error') }
        },

        openPart(p) {
          this.activePart = { ...p }
          this.partForm = { ...p }
          this.panel = 'part'
          this.panelMode = 'edit'
        },

        async savePart() {
          try {
            const res = await fetch(`/api/v1/inventory/parts/${this.activePart.id}`, {
              method: 'PUT',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(this.cleanPartData(this.partForm)),
            })
            if (!res.ok) throw new Error('Update failed')
            this.showToast('Part updated.', 'success')
            this.closePanel()
            await this.fetchInventoryStats()
          } catch(e) { this.showToast(e.message, 'error') }
        },

        async deletePart() {
          if (!confirm(`Delete part ${this.activePart.name}?`)) return
          try {
            await fetch(`/api/v1/inventory/parts/${this.activePart.id}`, { method: 'DELETE' })
            this.showToast('Part deleted.', 'success')
            this.closePanel()
            await this.fetchInventoryStats()
          } catch(e) { this.showToast(e.message, 'error') }
        },

        // ── Buy / Sell ────────────────────────────────────────────────────────
        bsDevices: [],
        openNewDevice() {
          this.resetBSForm()
          this.panel = 'buysell'
          this.panelMode = 'new'
        },

        resetBSForm() {
          this.bsForm = {
            customer_name: '', customer_phone: '', device: '',
            condition: 'Good', purchase_price: '', sell_price: '',
            status: 'Staging', notes: ''
          }
        },

        async submitDevice() {
          if (!this.bsForm.device) {
            this.showToast('Device name is required.', 'error')
            return
          }
          try {
            const payload = { ...this.bsForm }
            if (payload.purchase_price === '') payload.purchase_price = null
            if (payload.sell_price === '') payload.sell_price = null
            const res = await fetch('/api/v1/buy-sell/', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(payload),
            })
            if (!res.ok) throw new Error('Failed to add device')
            this.showToast('Device added.', 'success')
            this.closePanel()
            await this.fetchBuySellStats()
          } catch(e) { this.showToast(e.message, 'error') }
        },

        openDevice(d) {
          this.activeDevice = { ...d }
          this.bsForm = { ...d }
          this.panel = 'buysell'
          this.panelMode = 'edit'
        },

        async saveDevice() {
          try {
            const payload = { ...this.bsForm }
            if (payload.purchase_price === '') payload.purchase_price = null
            if (payload.sell_price === '') payload.sell_price = null
            const res = await fetch(`/api/v1/buy-sell/${this.activeDevice.id}`, {
              method: 'PUT',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(payload),
            })
            if (!res.ok) throw new Error('Update failed')
            this.showToast('Device updated.', 'success')
            this.closePanel()
            await this.fetchBuySellStats()
          } catch(e) { this.showToast(e.message, 'error') }
        },

        async deleteDevice() {
          if (!confirm(`Delete device ${this.activeDevice.device}?`)) return
          try {
            await fetch(`/api/v1/buy-sell/${this.activeDevice.id}`, { method: 'DELETE' })
            this.showToast('Device deleted.', 'success')
            this.closePanel()
            await this.fetchBuySellStats()
          } catch(e) { this.showToast(e.message, 'error') }
        },



        // Settings & Backups
        backups: [],

        startClock() {
          this.updateClock()
          setInterval(() => this.updateClock(), 1000)
        },
        updateClock() {
          const formatStr = this.config?.time_format === '24h' ? 'en-GB' : 'en-US'
          const tz = this.config?.timezone || 'America/New_York'
          try {
            this.currentTime = new Date().toLocaleString(formatStr, {
              timeZone: tz,
              hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: this.config?.time_format !== '24h'
            })
          } catch(e) {
            this.currentTime = new Date().toLocaleTimeString()
          }
        },
        applyDensity() {
          if (this.config?.display_density === 'compact') {
            document.body.classList.add('density-compact')
          } else {
            document.body.classList.remove('density-compact')
          }
        },
        async fetchConfig() {
          try {
            const res = await fetch('/api/settings/config')
            if (res.ok) {
              this.isOffline = false;
              const data = await res.json()
              this.config = data
              
              if (data.email_templates) {
                try {
                  this.emailTemplates = JSON.parse(data.email_templates)
                } catch(e) { this.emailTemplates = [] }
              }
              this.applyDensity()
              this.updateClock()
            } else {
              this.isOffline = true;
            }
          } catch(e) {
            console.error('Failed to load config', e);
            this.isOffline = true;
          }
          try {
            if (this.auth.user?.role === 'owner') {
              const sr = await fetch('/api/settings/system-info')
              if (sr.ok) {
                this.isOffline = false;
                this.systemInfo = await sr.json()
              }
              const br = await fetch('/api/settings/backups/info')
              if (br.ok) {
                this.isOffline = false;
                this.backupInfo = await br.json()
              }
              const pr = await fetch('/api/settings/auth/pins')
              if (pr.ok) {
                this.isOffline = false;
                this.pinsList = await pr.json()
              }
            }
          } catch(e){
            console.error('Failed to load owner config settings', e);
            this.isOffline = true;
          }
        },
        async saveConfig() {
          try {
            const payload = { ...this.config }
            if (this.emailTemplates) {
              payload.email_templates = JSON.stringify(this.emailTemplates)
            }
            const res = await fetch('/api/settings/config', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(payload)
            })
            if (res.ok) this.showToast('Settings saved', 'success')
            else this.showToast('Failed to save settings', 'error')
          } catch(e) { this.showToast('Error', 'error') }
        },
        async saveEmailTemplates() {
          this.saveConfig()
        },
        async addPin() {
          if (!this.newPin.label || !this.newPin.pin) {
            this.showToast('Please fill all fields', 'error');
            return;
          }
          if (!/^\d{6}$/.test(this.newPin.pin)) {
            this.showToast('PIN must be exactly 6 digits', 'error');
            return;
          }
          try {
            const res = await fetch('/api/settings/auth/pins', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(this.newPin)
            })
            if (res.ok) {
              this.showToast('User added', 'success')
              this.newPin = { label: '', role: 'technician', pin: '' }
              this.showAddPin = false
              await this.fetchConfig()
            } else {
              const data = await res.json()
              this.showToast(data.error || 'Failed', 'error')
            }
          } catch(e) { this.showToast('Error', 'error') }
        },
        async deletePin(id) {
          if (!confirm("Are you sure?")) return
          try {
            const res = await fetch(`/api/settings/auth/pins/${id}`, { method: 'DELETE' })
            if (res.ok) {
              this.showToast('User deleted', 'success')
              await this.fetchConfig()
            } else {
              const data = await res.json()
              this.showToast(data.error || 'Failed', 'error')
            }
          } catch(e) { this.showToast('Error', 'error') }
        },
        async revokeOtherSessions() {
          if (!confirm("Log out all other devices?")) return
          try {
            const res = await fetch('/api/settings/sessions/revoke-others', { method: 'POST' })
            if (res.ok) {
              this.showToast('Other sessions revoked', 'success')
              await this.fetchConfig()
            } else this.showToast('Failed', 'error')
          } catch(e) { this.showToast('Error', 'error') }
        },
        async exportAllData() {
          window.location.href = '/api/settings/export/all'
          this.showToast('Preparing download...', 'info')
        },
        async exportModule(mod) {
          window.location.href = `/api/settings/export/${mod}`
        },
        async resetModule() {
          if (this.dangerModuleConfirm !== 'DELETE' || !this.dangerModule) return
          try {
            const res = await fetch('/api/settings/danger/reset-module', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ module: this.dangerModule, confirmation: 'DELETE' })
            })
            if (res.ok) {
              this.showToast('Module reset successful.', 'success')
              this.dangerModuleConfirm = ''
              this.dangerModule = ''
              await this.fetchTickets()
              await this.fetchStats()
              if (this.fetchInventoryStats) await this.fetchInventoryStats()
              if (this.fetchBuySellStats)   await this.fetchBuySellStats()
              if (this.fetchFinanceSummary) await this.fetchFinanceSummary()
              if (this.fetchCustomers)      await this.fetchCustomers()
              setTimeout(() => { window.location.reload() }, 1000)
            } else {
              this.showToast('Reset failed', 'error')
            }
          } catch(e) { this.showToast('Error', 'error') }
        },
        async resetAllData() {
          if (this.dangerAllConfirm !== 'DELETE EVERYTHING') return
          try {
            const res = await fetch('/api/settings/danger/reset-all', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ confirmation: 'DELETE EVERYTHING' })
            })
            if (res.ok) {
              this.showToast('Database nuked. Logging out...', 'success')
              setTimeout(() => { window.location.reload() }, 2000)
            } else {
              this.showToast('Reset failed', 'error')
            }
          } catch(e) { this.showToast('Error', 'error') }
        },
        async restoreBackup(event) {
          const file = event.target.files[0]
          if (!file) return
          const formData = new FormData()
          formData.append('file', file)
          
          this.showToast('Restoring backup...', 'info')
          try {
            const res = await fetch('/api/settings/backups/restore', {
              method: 'POST',
              body: formData
            })
            if (res.ok) {
              this.showToast('Database restored! Please refresh the page.', 'success')
            } else {
              const data = await res.json()
              this.showToast(data.error || 'Restore failed', 'error')
            }
          } catch(e) { this.showToast('Error', 'error') }
          event.target.value = ''
        },
        async logout() {
          try {
            await fetch('/api/settings/auth/logout', { method: 'POST' })
            window.location.reload()
          } catch(e) { this.showToast('Error', 'error') }
        },

        async fetchBackups() {
          try {
            const res = await fetch('/api/settings/backups')
            this.backups = await res.json()
          } catch(e) {}
        },

        async createBackup() {
          try {
            const res = await fetch('/api/settings/backups', { method: 'POST' })
            if (!res.ok) throw new Error('Backup failed')
            this.showToast('Backup created.', 'success')
            await this.fetchBackups()
            await this.fetchConfig()
          } catch(e) { this.showToast(e.message, 'error') }
        },

        // ── Ticket panel ──────────────────────────────────────────────────────
        async openTicket(t) {
          this.activeTicket = t
          this.panelMode    = 'view'
          this.panel        = 'ticket'
          this.repairLog    = []
          this.logEntry     = { status: 'In Progress', note: '' }
          this.ticketPhotos = []
          this.photoDropdownOpen = false
          this.qrModalOpen = false
          if (this.pollTimer) clearInterval(this.pollTimer)
          // fetch fresh copy
          try {
            const res = await fetch(`/api/v1/repair-tickets/${t.id}`)
            if (res.ok) this.activeTicket = await res.json()
          } catch(e) {}
          // fetch log
          try {
            const lr = await fetch(`/api/v1/repair-tickets/${t.id}/log`)
            if (lr.ok) this.repairLog = await lr.json()
          } catch(e) {}
          // fetch photos
          try {
            await this.fetchPhotos(t.id)
          } catch(e) {}
        },

        openNewTicket() {
          this.resetForm()
          this.panel = 'new'
        },

        closePanel() {
          this.panel = null
          this.activeTicket = null
          this.panelMode = 'view'
          this.qrModalOpen = false
          if (this.pollTimer) clearInterval(this.pollTimer)
          this.customerQuery = ''
          this.customerSuggestions = []
          this.selectedSuggestionIndex = -1
        },
        
        async fetchPhotos(ticketId) {
          try {
            const res = await fetch(`/api/v1/repair-tickets/${ticketId}/photos`);
            if (res.ok) this.ticketPhotos = await res.json();
          } catch(e) {}
        },
        
        async uploadFromDesktop(files) {
          if (!files || files.length === 0) return;
          for (let i = 0; i < files.length; i++) {
            const fd = new FormData();
            fd.append('file', files[i]);
            try {
              await fetch(`/api/v1/repair-tickets/${this.activeTicket.id}/photos`, { method: 'POST', body: fd });
            } catch(e) { this.showToast('Upload failed', 'error'); }
          }
          await this.fetchPhotos(this.activeTicket.id);
          this.showToast('Photos uploaded', 'success');
        },
        
        async startQrSession() {
          try {
            const res = await fetch(`/api/v1/repair-tickets/${this.activeTicket.id}/upload-session`, { method: 'POST' });
            if (!res.ok) throw new Error("Failed to start session");
            this.qrSession = await res.json();
            this.qrModalOpen = true;
            this.pollTimer = setInterval(() => this.pollSession(), 3000);
          } catch(e) {
            this.showToast(e.message, 'error');
          }
        },
        
        async pollSession() {
          if (!this.qrSession || !this.qrModalOpen) return;
          try {
            const res = await fetch(`/api/v1/repair-tickets/${this.activeTicket.id}/upload-session/${this.qrSession.token}/status`);
            if (res.ok) {
              const data = await res.json();
              if (data.received && data.count > (this.qrSession.count || 0)) {
                this.qrSession.received = true;
                this.qrSession.count = data.count;
                await this.fetchPhotos(this.activeTicket.id);
              }
            }
          } catch(e) {}
        },
        
        closeQrModal() {
          this.qrModalOpen = false;
          if (this.pollTimer) clearInterval(this.pollTimer);
        },
        
        async deletePhoto(filename) {
          if (!confirm("Delete this photo?")) return;
          try {
            const res = await fetch(`/api/v1/repair-tickets/${this.activeTicket.id}/photos/${filename}`, { method: 'DELETE' });
            if (res.ok) {
              this.showToast('Photo deleted', 'success');
              await this.fetchPhotos(this.activeTicket.id);
            }
          } catch(e) {
            this.showToast('Failed to delete photo', 'error');
          }
        },

        prefillEdit() {
          this.editForm = { ...this.activeTicket }
        },

        async saveEdit() {
          try {
            if (this.editForm.price !== undefined && this.editForm.price !== null) {
              const cleanPrice = this.editForm.price.toString().replace(/[^0-9.]/g, '');
              const parsedPrice = parseFloat(cleanPrice);
              this.editForm.price = isNaN(parsedPrice) ? '' : `$${parsedPrice.toFixed(2)}`;
            }
            const res = await fetch(`/api/v1/repair-tickets/${this.activeTicket.id}`, {
              method: 'PUT',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(this.editForm),
            })
            if (!res.ok) throw new Error('Save failed')
            this.showToast('Ticket updated.', 'success')
            this.activeTicket = { ...this.editForm }
            this.panelMode = 'view'
            await this.fetchTickets()
            await this.fetchStats()
          } catch(e) { this.editForm = { ...this.activeTicket }; this.showToast(e.message, 'error') }
        },

        async quickStatus(s) {
          try {
            const res = await fetch(`/api/v1/repair-tickets/${this.activeTicket.id}/status`, {
              method: 'PATCH',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ status: s }),
            })
            if (!res.ok) throw new Error('Status update failed')
            this.activeTicket = { ...this.activeTicket, status: s }
            this.showToast(`Status → ${s}`, 'success')
            await this.fetchTickets()
            await this.fetchStats()
          } catch(e) { this.showToast(e.message, 'error') }
        },

        async deleteTicket() {
          if (!confirm(`Delete ticket ${this.activeTicket.id}? This cannot be undone.`)) return
          try {
            await fetch(`/api/v1/repair-tickets/${this.activeTicket.id}`, { method: 'DELETE' })
            this.showToast('Ticket deleted.', 'success')
            this.closePanel()
            await this.fetchTickets()
            await this.fetchStats()
          } catch(e) { this.showToast(e.message, 'error') }
        },

        async addLog() {
          if (!this.logEntry.note.trim()) return
          try {
            const res = await fetch(`/api/v1/repair-tickets/${this.activeTicket.id}/log`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(this.logEntry),
            })
            if (!res.ok) throw new Error('Log failed')
            
            const isResolution = this.logEntry.status === 'Resolution'
            this.logEntry.note = ''
            
            const lr = await fetch(`/api/v1/repair-tickets/${this.activeTicket.id}/log`)
            this.repairLog = await lr.json()
            this.showToast('Log entry added.', 'success')
            
            if (isResolution && this.activeTicket.status !== 'Completed') {
              await this.quickStatus('Completed')
            }
          } catch(e) { this.showToast(e.message, 'error') }
        },

        async printInvoice() {
          try {
            const res = await fetch(`/api/invoices/${this.activeTicket.id}`, { method: 'POST' })
            if (!res.ok) throw new Error('Invoice generation failed')
            const blob = await res.blob()
            const url  = URL.createObjectURL(blob)
            window.open(url, '_blank')
          } catch(e) { this.showToast(e.message, 'error') }
        },

        async syncCalendar() {
          try {
            const res = await fetch(`/api/calendar/sync/${this.activeTicket.id}`, { method: 'POST' })
            if (!res.ok) {
              const err = await res.json()
              throw new Error(err.detail || 'Sync failed')
            }
            const data = await res.json()
            this.showToast('Synced to Google Calendar.', 'success')
            if (data.html_link) window.open(data.html_link, '_blank')
          } catch(e) { this.showToast(e.message, 'error') }
        },

        // ── New ticket ────────────────────────────────────────────────────────
        async searchCustomerSuggestions() {
          const query = this.customerQuery
          if (!query || query.trim().length < 1) {
            this.customerSuggestions = []
            this.selectedSuggestionIndex = -1
            return
          }
          try {
            const res = await fetch(`/api/customers/?search=${encodeURIComponent(query)}`)
            if (res.ok) {
              this.customerSuggestions = await res.json()
            } else {
              this.customerSuggestions = []
            }
          } catch(e) {
            this.customerSuggestions = []
          }
          this.selectedSuggestionIndex = -1
        },

        selectCustomerSuggestion(cust) {
          this.form.name = cust.name || ''
          this.form.phone = cust.phone || ''
          this.form.email = cust.email || ''
          this.form.address = cust.address || ''
          this.customerSuggestions = []
          this.selectedSuggestionIndex = -1
          this.customerQuery = ''
        },

        onRepairChange() {
          const price = this.REPAIR_PRICE[this.form.repair]
          const days  = this.REPAIR_DAYS[this.form.repair]
          if (price !== null && price !== undefined) {
            this.form.price = price.toString()
            this.repairHint = `Standard rate: $${price} — edit if needed`
          } else {
            this.form.price = ''
            this.repairHint = 'Custom repair — enter price manually'
          }
          this.form.due = addBizDays(days) ?? ''
        },

        async submitTicket() {
          if (!this.form.name || !this.form.phone || !this.form.device || !this.form.repair) {
            this.showToast('Name, phone, device, and repair type are required.', 'error')
            return
          }
          this.submitting = true
          try {
            const cleanPrice = this.form.price ? this.form.price.toString().replace(/[^0-9.]/g, '') : '';
            const parsedPrice = parseFloat(cleanPrice);
            const payload = {
              ...this.form,
              price: isNaN(parsedPrice) ? '' : `$${parsedPrice.toFixed(2)}`,
            }
            const res = await fetch('/api/v1/repair-tickets/', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(payload),
            })
            if (!res.ok) {
              const err = await res.json()
              throw new Error(err.error ?? 'Failed to create ticket')
            }
            const data = await res.json()
            this.showToast(`Ticket ${data.id} created.`, 'success')
            this.closePanel()
            this.resetForm()
            await this.fetchTickets()
            await this.fetchStats()
          } catch(e) {
            this.showToast(e.message, 'error')
          } finally {
            this.submitting = false
          }
        },

        resetForm() {
          let pre_repair = {}
          this.TICKET_CHECKLIST.forEach(k => pre_repair[k] = null)
          
          let legal = {}
          this.TICKET_LEGAL.forEach(k => legal[k] = false)

          this.form = {
            priority:'Standard', name:'', phone:'', email:'',
            address:'', device:'', serial:'', repair:'',
            price:'', issue:'', notes:'',
            technician:'', due:'',
            tax_exempt: false,
            discount_type: 'None',
            custom_data: '{}',
            pre_repair_json: JSON.stringify(pre_repair),
            legal_json: JSON.stringify(legal)
          }
          this.repairHint = ''
          this.customerQuery = ''
          this.customerSuggestions = []
          this.selectedSuggestionIndex = -1
        },

        getChecklist(jsonStr) {
          try { return JSON.parse(jsonStr || '{}') } catch(e) { return {} }
        },
        updateChecklist(obj, key, val) {
          let current = this.getChecklist(obj.pre_repair_json)
          current[key] = val
          obj.pre_repair_json = JSON.stringify(current)
        },
        getLegal(jsonStr) {
          try { return JSON.parse(jsonStr || '{}') } catch(e) { return {} }
        },
        updateLegal(obj, key, val) {
          let current = this.getLegal(obj.legal_json)
          current[key] = val
          obj.legal_json = JSON.stringify(current)
        },

        // Customers
        activeCustomer: null,
        custStats: { total: 0, completed: 0, revenue: '$0.00' },
        custTickets: [],

        async openCustomer(c) {
          this.activeCustomer = { ...c }
          this.panel = 'customer'
          this.panelMode = 'view'
          
          try {
            const [sRes, tRes] = await Promise.all([
              fetch(`/api/customers/${c.phone}/stats`),
              fetch(`/api/customers/${c.phone}/tickets`)
            ])
            if (sRes.ok) this.custStats = await sRes.json()
            if (tRes.ok) this.custTickets = await tRes.json()
          } catch(e) { this.showToast('Failed to load customer details', 'error') }
        },

        async saveCustomerNotes() {
          try {
            const res = await fetch(`/api/customers/${this.activeCustomer.phone}/notes`, {
              method: 'PATCH',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ notes: this.activeCustomer.notes }),
            })
            if (!res.ok) throw new Error('Save failed')
            this.showToast('Notes saved.', 'success')
          } catch(e) { this.showToast(e.message, 'error') }
        },

        // Email
        emailTmpl: '',
        emailForm: { subject: '', body: '' },

        openEmailComposer() {
          this.panel = 'email'
          if (this.emailTemplates && this.emailTemplates.length > 0) {
            this.selectEmailTemplate(0)
          }
        },

        selectEmailTemplate(idx) {
          this.emailTmpl = idx
          const tmpl = this.emailTemplates[idx]
          if (!tmpl) return
          const t = this.activeTicket
          const shopName = this.config?.shop_name || 'OpenBench'
          const shopPhone = this.config?.shop_phone || ''
          
          const fill = (str) => {
            return str.replace(/\[TICKET_ID\]/g, t.id)
                      .replace(/\[CUSTOMER_NAME\]/g, (t.name || 'Customer').split(' ')[0])
                      .replace(/\[DEVICE\]/g, t.device || 'your device')
                      .replace(/\[PRICE\]/g, t.price || '$0.00')
                      .replace(/\[STATUS\]/g, t.status || 'In Progress')
          }

          this.emailForm.subject = fill(tmpl.subject)
          this.emailForm.body = fill(tmpl.body)
        },

        sendEmail() {
          if (!this.activeTicket.email) {
            this.showToast('Customer has no email on file.', 'error')
            return
          }
          const params = new URLSearchParams({
            subject: this.emailForm.subject,
            body: this.emailForm.body
          })
          window.open(`mailto:${this.activeTicket.email}?${params.toString()}`, '_blank')
        },

        // QR Labels
        printLabel() {
          const t = this.activeTicket
          const escapeHtml = (str) => {
            if (!str) return '';
            return str.toString()
              .replace(/&/g, '&amp;')
              .replace(/</g, '&lt;')
              .replace(/>/g, '&gt;')
              .replace(/"/g, '&quot;')
              .replace(/'/g, '&#039;');
          };
          const idEscaped = escapeHtml(t.id);
          const nameEscaped = escapeHtml(t.name);
          const deviceEscaped = escapeHtml(t.device);
          const idEncoded = encodeURIComponent(t.id);

          const labelHtml = `
            <div style="width: 2.25in; height: 1.25in; padding: 0.1in; font-family: 'JetBrains Mono', monospace; text-align: center; border: 1px solid #eee;">
              <div style="font-size: 14px; font-weight: bold; margin-bottom: 5px;">30 OR LESS</div>
              <div style="font-size: 11px; margin-bottom: 5px;">${idEscaped}</div>
              <img src="/api/qrcode?data=${idEncoded}" style="width: 60px; height: 60px; margin-bottom: 5px;" />
              <div style="font-size: 10px;">${nameEscaped}</div>
              <div style="font-size: 9px; color: #666;">${deviceEscaped}</div>
            </div>
          `
          const win = window.open('', '_blank', 'width=300,height=300')
          win.document.write(`<html><body onload="window.print();window.close()">${labelHtml}</body></html>`)
          win.document.close()
        },

        getGuestPortalUrl() {
          const port = window.location.port;
          const portStr = (port && port !== '80' && port !== '443') ? `:${port}` : '';
          return `http://[your-local-ip]${portStr}/tools`;
        },

        // Calendar
        async getCalendarLinks() {
          const t = this.activeTicket
          if (!t.due || t.due === '—') return null
          
          // Simple date parser for our format "Sat, Jun 13 2026"
          const parseDue = (s) => {
            try {
              const d = new Date(s)
              return d.toISOString().replace(/-|:|\.\d\d\d/g, "")
            } catch(e) { return null }
          }
          
          const start = parseDue(t.due)
          if (!start) return null
          
          const details = encodeURIComponent(`Repair Ticket: ${t.id}\nDevice: ${t.device}\nCustomer: ${t.name}`)
          const summary = encodeURIComponent(`[${t.id}] ${t.repair}`)
          
          return {
            google: `https://www.google.com/calendar/render?action=TEMPLATE&text=${summary}&dates=${start}/${start}&details=${details}&sf=true&output=xml`,
            outlook: `https://outlook.live.com/calendar/0/deeplink/compose?path=/calendar/action/compose&rru=addevent&subject=${summary}&startdt=${start}&enddt=${start}&body=${details}`,
          }
        },

        async openCalendarLink(type) {
          const links = await this.getCalendarLinks()
          if (links && links[type]) window.open(links[type], '_blank')
          else this.showToast('Invalid due date for calendar', 'error')
        },

        // ── Styling helpers ───────────────────────────────────────────────────
        railClass(status) {
          return {
            'Open':             'rail-open',
            'In Progress':      'rail-progress',
            'Waiting on Parts': 'rail-parts',
            'Ready for Pickup': 'rail-pickup',
            'Completed':        'rail-completed',
            'Cancelled':        'rail-cancelled',
          }[status] ?? ''
        },

        badgeClass(status) {
          return {
            'Open':             'badge-open',
            'In Progress':      'badge-progress',
            'Waiting on Parts': 'badge-parts',
            'Ready for Pickup': 'badge-pickup',
            'Completed':        'badge-completed',
            'Cancelled':        'badge-cancelled',
            'Resolution':       'badge-completed',
          }[status] ?? ''
        },

        priorityClass(p) {
          return {
            'Standard': 'priority-standard',
            'Rush':     'priority-rush',
            'Critical': 'priority-critical',
          }[p] ?? ''
        },

        // ── Toast ─────────────────────────────────────────────────────────────
        showToast(msg, type = 'success') {
          this.toastMsg     = msg
          this.toastType    = type
          this.toastVisible = true
          if (this._toastTimer) clearTimeout(this._toastTimer)
          this._toastTimer = setTimeout(() => { this.toastVisible = false }, 3000)
        },
      }
    }
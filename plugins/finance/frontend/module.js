(function() {
  // Try to access the Alpine app instance
  let app = null;
  if (window.Alpine) {
    try {
      app = window.Alpine.$data(document.body);
    } catch (e) {
      console.error("[Finance Plugin] Error accessing Alpine via $data:", e);
    }
  }
  if (!app) {
    const rootEl = document.querySelector('body');
    if (rootEl && rootEl.__x && rootEl.__x.$data) {
      app = rootEl.__x.$data;
    }
  }

  if (!app) {
    console.error("[Finance Plugin] Alpine app instance not found.");
    return;
  }

  // Initialize Finance State Variables
  app.finSummary = {};
  app.finRange = 'week';
  app.expenses = [];
  app.expenseSortBy = 'date';
  app.expenseSortDesc = true;
  app.expenseForm = {};
  app.activeExpense = null;
  app.FINANCE_CATEGORIES = [];

  // Fetch Finance Summary and Categories
  app.fetchFinanceSummary = async function() {
    try {
      let url = '/api/v1/finance/summary';
      if (this.finRange === 'week') {
        const now = new Date();
        const first = now.getDate() - now.getDay(); // Sunday
        const start = new Date(now.setDate(first)).toISOString().split('T')[0];
        url += `?frm=${start}`;
      }
      const res = await fetch(url);
      this.finSummary = await res.json();
      await this.fetchExpenses();
      if (this.FINANCE_CATEGORIES.length === 0) {
        const cr = await fetch('/api/v1/finance/categories');
        this.FINANCE_CATEGORIES = await cr.json();
      }
    } catch(e) {
      console.error("[Finance Plugin] Failed to fetch summary:", e);
    }
  };

  // Fetch Expense Log
  app.fetchExpenses = async function() {
    try {
      const res = await fetch('/api/v1/finance/expenses');
      this.expenses = await res.json();
      this.sortExpenses();
    } catch(e) {
      console.error("[Finance Plugin] Failed to fetch expenses:", e);
    }
  };

  // Open New Expense Modal/Panel
  app.openNewExpense = function() {
    this.resetExpenseForm();
    this.panel = 'expense';
    this.panelMode = 'new';
  };

  // Reset Expense Form State
  app.resetExpenseForm = function() {
    this.expenseForm = {
      date: new Date().toISOString().split('T')[0],
      description: '',
      amount: '',
      category: 'Operating Expense',
      source: 'Manual',
      notes: ''
    };
  };

  // Submit/Create New Expense
  app.submitExpense = async function() {
    if (!this.expenseForm.description || !this.expenseForm.amount) {
      this.showToast('Description and amount are required.', 'error');
      return;
    }
    try {
      const res = await fetch('/api/v1/finance/expenses', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(this.expenseForm),
      });
      if (!res.ok) throw new Error('Failed to add expense');
      this.showToast('Expense added.', 'success');
      this.closePanel();
      await this.fetchFinanceSummary();
    } catch(e) {
      this.showToast(e.message, 'error');
    }
  };

  // Open Edit Expense Modal/Panel
  app.openExpense = function(e) {
    this.activeExpense = { ...e };
    this.expenseForm = { ...e };
    this.panel = 'expense';
    this.panelMode = 'edit';
  };

  // Save/Update Existing Expense
  app.saveExpense = async function() {
    try {
      const res = await fetch(`/api/v1/finance/expenses/${this.activeExpense.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(this.expenseForm),
      });
      if (!res.ok) throw new Error('Update failed');
      this.showToast('Expense updated.', 'success');
      this.closePanel();
      await this.fetchFinanceSummary();
    } catch(e) {
      this.showToast(e.message, 'error');
    }
  };

  // Delete Expense
  app.deleteExpense = async function() {
    if (!confirm(`Delete expense "${this.activeExpense.description}"?`)) return;
    try {
      await fetch(`/api/v1/finance/expenses/${this.activeExpense.id}`, { method: 'DELETE' });
      this.showToast('Expense deleted.', 'success');
      this.closePanel();
      await this.fetchFinanceSummary();
    } catch(e) {
      this.showToast(e.message, 'error');
    }
  };

  // Sort Expense log locally
  app.sortExpenses = function() {
    if (!this.expenseSortBy) return;

    const field = this.expenseSortBy;
    const desc = this.expenseSortDesc;

    this.expenses.sort((a, b) => {
      let valA = a[field];
      let valB = b[field];

      const isAEmpty = valA === undefined || valA === null || valA === '' || valA === '—';
      const isBEmpty = valB === undefined || valB === null || valB === '' || valB === '—';

      if (isAEmpty && isBEmpty) return 0;
      if (isAEmpty) return 1;
      if (isBEmpty) return -1;

      let res = 0;

      if (field === 'amount') {
        res = parseFloat(valA) - parseFloat(valB);
      } else if (field === 'date') {
        const dateA = new Date(Date.parse(valA));
        const dateB = new Date(Date.parse(valB));
        res = dateA - dateB;
      } else {
        res = valA.toString().localeCompare(valB.toString(), undefined, { sensitivity: 'base' });
      }

      return desc ? -res : res;
    });
  };

  // Toggle Column Sort Order
  app.toggleExpenseSort = function(field) {
    if (this.expenseSortBy === field) {
      this.expenseSortDesc = !this.expenseSortDesc;
    } else {
      this.expenseSortBy = field;
      this.expenseSortDesc = false;
    }
    this.sortExpenses();
  };

  // Export Finance CSV
  app.exportFinance = async function() {
    window.location.href = '/api/v1/finance/export';
    this.showToast('Exporting finance data...', 'info');
  };
})();

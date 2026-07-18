class DeskDotCard extends HTMLElement {
  setConfig(config) {
    if (!config.entity) {
      throw new Error("Please define an entity (sensor.deskdot_XXXX_card_inventory)");
    }
    this._config = config;
    this._entity = config.entity;
    this._editing = null;
    this._showForm = false;
  }

  set hass(hass) {
    this._hass = hass;
    const state = hass.states[this._entity];
    if (!state) {
      this._renderError("Entity not found: " + this._entity);
      return;
    }
    this._cards = state.attributes.cards || [];
    this._deviceId = null;
    const entityEntry = Object.values(hass.entities || {}).find(
      (e) => e.entity_id === this._entity
    );
    if (entityEntry) this._deviceId = entityEntry.device_id;
    this._render();
  }

  static getStubConfig() {
    return { entity: "" };
  }

  getCardSize() {
    return Math.max(3, (this._cards || []).length + 2);
  }

  _render() {
    if (!this.shadowRoot) {
      this.attachShadow({ mode: "open" });
    }

    const cards = this._cards || [];

    this.shadowRoot.innerHTML = `
      <ha-card>
        <div class="header">
          <span class="title">DeskDot Cards</span>
          <span class="count">${cards.length} card${cards.length !== 1 ? "s" : ""}</span>
          <button class="add-btn" title="Add card">+</button>
        </div>
        <div class="card-list">
          ${cards.length === 0
            ? '<div class="empty">No cards on device</div>'
            : cards.map((card) => this._renderCardRow(card)).join("")}
        </div>
        ${this._showForm ? this._renderForm() : ""}
      </ha-card>
      <style>
        ha-card { padding: 16px; }
        .header {
          display: flex;
          align-items: center;
          margin-bottom: 12px;
        }
        .title { font-size: 18px; font-weight: 500; flex: 1; }
        .count {
          font-size: 13px;
          color: var(--secondary-text-color);
          margin-right: 12px;
        }
        .add-btn {
          width: 32px; height: 32px;
          border-radius: 50%;
          border: none;
          background: var(--primary-color);
          color: white;
          font-size: 20px;
          cursor: pointer;
          display: flex;
          align-items: center;
          justify-content: center;
          line-height: 1;
        }
        .add-btn:hover { opacity: 0.85; }
        .card-list { display: flex; flex-direction: column; gap: 8px; }
        .empty {
          text-align: center;
          padding: 24px;
          color: var(--secondary-text-color);
        }
        .card-row {
          display: flex;
          align-items: center;
          padding: 10px 12px;
          border-radius: 8px;
          background: var(--card-background-color, var(--ha-card-background));
          border: 1px solid var(--divider-color);
          gap: 12px;
        }
        .card-row.disabled { opacity: 0.5; }
        .card-icon {
          width: 24px; height: 24px;
          display: flex; align-items: center; justify-content: center;
          color: var(--primary-text-color);
          flex-shrink: 0;
        }
        .card-info { flex: 1; min-width: 0; }
        .card-id {
          font-weight: 500;
          font-size: 14px;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }
        .card-text {
          font-size: 12px;
          color: var(--secondary-text-color);
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }
        .card-meta {
          font-size: 11px;
          color: var(--secondary-text-color);
        }
        .card-actions { display: flex; gap: 4px; flex-shrink: 0; }
        .icon-btn {
          width: 32px; height: 32px;
          border: none;
          background: none;
          cursor: pointer;
          border-radius: 4px;
          display: flex;
          align-items: center;
          justify-content: center;
          color: var(--primary-text-color);
          font-size: 16px;
        }
        .icon-btn:hover { background: var(--divider-color); }
        .icon-btn.danger:hover { background: #f443361a; color: #f44336; }

        .form-overlay {
          margin-top: 16px;
          padding: 16px;
          border: 1px solid var(--divider-color);
          border-radius: 8px;
          background: var(--card-background-color, var(--ha-card-background));
        }
        .form-title {
          font-size: 16px; font-weight: 500; margin-bottom: 12px;
        }
        .form-grid {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 8px;
        }
        .form-grid .full { grid-column: 1 / -1; }
        .form-field label {
          display: block;
          font-size: 12px;
          color: var(--secondary-text-color);
          margin-bottom: 4px;
        }
        .form-field input,
        .form-field select {
          width: 100%;
          padding: 8px;
          border: 1px solid var(--divider-color);
          border-radius: 4px;
          background: var(--primary-background-color);
          color: var(--primary-text-color);
          font-size: 14px;
          box-sizing: border-box;
        }
        .form-actions {
          display: flex;
          gap: 8px;
          margin-top: 12px;
          justify-content: flex-end;
        }
        .form-actions button {
          padding: 8px 16px;
          border-radius: 4px;
          border: none;
          cursor: pointer;
          font-size: 14px;
        }
        .btn-primary {
          background: var(--primary-color);
          color: white;
        }
        .btn-secondary {
          background: var(--divider-color);
          color: var(--primary-text-color);
        }
      </style>
    `;

    this.shadowRoot.querySelector(".add-btn").addEventListener("click", () => {
      this._editing = null;
      this._showForm = true;
      this._render();
    });

    this.shadowRoot.querySelectorAll(".toggle-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const id = btn.dataset.id;
        const enabled = btn.dataset.enabled === "true";
        this._toggleCard(id, !enabled);
      });
    });

    this.shadowRoot.querySelectorAll(".edit-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const card = this._cards.find((c) => c.id === btn.dataset.id);
        if (card) {
          this._editing = card;
          this._showForm = true;
          this._render();
        }
      });
    });

    this.shadowRoot.querySelectorAll(".delete-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        if (confirm(`Delete card "${btn.dataset.id}"?`)) {
          this._deleteCard(btn.dataset.id);
        }
      });
    });

    if (this._showForm) {
      const form = this.shadowRoot.querySelector(".form-overlay");
      form.querySelector(".cancel-btn").addEventListener("click", () => {
        this._showForm = false;
        this._editing = null;
        this._render();
      });
      form.querySelector(".save-btn").addEventListener("click", () => {
        this._saveCard();
      });
    }
  }

  _renderCardRow(card) {
    const enabled = card.enabled !== false;
    const typeIcon = card.type === "clock" ? "\u{1F552}"
      : card.type === "pixel" ? "\u{1F3A8}" : "\u{1F4DD}";
    return `
      <div class="card-row ${enabled ? "" : "disabled"}">
        <div class="card-icon">${typeIcon}</div>
        <div class="card-info">
          <div class="card-id">${card.id}</div>
          <div class="card-text">${card.text || ""}</div>
          <div class="card-meta">
            ${card.type || "text"} &middot; priority ${card.priority ?? 50}
            ${card.duration ? " &middot; " + card.duration + "s" : ""}
            ${card.icon ? " &middot; icon: " + card.icon : ""}
          </div>
        </div>
        <div class="card-actions">
          <button class="icon-btn toggle-btn" data-id="${card.id}" data-enabled="${enabled}" title="${enabled ? "Disable" : "Enable"}">
            ${enabled ? "\u{1F7E2}" : "⚪"}
          </button>
          <button class="icon-btn edit-btn" data-id="${card.id}" title="Edit">
            ✏️
          </button>
          <button class="icon-btn danger delete-btn" data-id="${card.id}" title="Delete">
            \u{1F5D1}
          </button>
        </div>
      </div>
    `;
  }

  _renderForm() {
    const c = this._editing || {};
    return `
      <div class="form-overlay">
        <div class="form-title">${this._editing ? "Edit Card" : "New Card"}</div>
        <div class="form-grid">
          <div class="form-field">
            <label>Card ID</label>
            <input name="card_id" value="${c.id || ""}" ${this._editing ? "readonly" : ""} placeholder="my_card" />
          </div>
          <div class="form-field">
            <label>Type</label>
            <select name="type">
              <option value="text" ${(c.type || "text") === "text" ? "selected" : ""}>Text</option>
              <option value="clock" ${c.type === "clock" ? "selected" : ""}>Clock</option>
              <option value="pixel" ${c.type === "pixel" ? "selected" : ""}>Pixel</option>
            </select>
          </div>
          <div class="form-field full">
            <label>Text</label>
            <input name="text" value="${c.text || ""}" placeholder="Card text content" />
          </div>
          <div class="form-field">
            <label>Icon</label>
            <input name="icon" value="${c.icon || ""}" placeholder="sun, rain, etc." />
          </div>
          <div class="form-field">
            <label>Color</label>
            <input name="color" type="color" value="${c.color || "#ffffff"}" />
          </div>
          <div class="form-field">
            <label>Duration (seconds)</label>
            <input name="duration" type="number" min="1" max="120" value="${c.duration || 10}" />
          </div>
          <div class="form-field">
            <label>Priority (0-100)</label>
            <input name="priority" type="number" min="0" max="100" value="${c.priority ?? 50}" />
          </div>
        </div>
        <div class="form-actions">
          <button class="btn-secondary cancel-btn">Cancel</button>
          <button class="btn-primary save-btn">${this._editing ? "Update" : "Create"}</button>
        </div>
      </div>
    `;
  }

  _renderError(msg) {
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    this.shadowRoot.innerHTML = `
      <ha-card>
        <div style="padding:16px;color:var(--error-color)">${msg}</div>
      </ha-card>
    `;
  }

  _toggleCard(cardId, enabled) {
    if (!this._deviceId) return;
    this._hass.callService("deskdot", "card", {
      device: this._deviceId,
      card_id: cardId,
      enabled: enabled,
    });
  }

  _deleteCard(cardId) {
    if (!this._deviceId) return;
    this._hass.callService("deskdot", "delete_card", {
      device: this._deviceId,
      card_id: cardId,
    });
  }

  _saveCard() {
    if (!this._deviceId) return;
    const form = this.shadowRoot.querySelector(".form-overlay");
    const data = {
      device: this._deviceId,
      card_id: form.querySelector('[name="card_id"]').value.trim(),
      type: form.querySelector('[name="type"]').value,
      text: form.querySelector('[name="text"]').value.trim(),
      icon: form.querySelector('[name="icon"]').value.trim() || undefined,
      color: form.querySelector('[name="color"]').value,
      duration: parseInt(form.querySelector('[name="duration"]').value) || 10,
      priority: parseInt(form.querySelector('[name="priority"]').value) || 50,
    };

    if (!data.card_id) {
      alert("Card ID is required");
      return;
    }
    if (!data.text && data.type !== "pixel") {
      alert("Text is required for text and clock cards");
      return;
    }

    Object.keys(data).forEach((k) => data[k] === undefined && delete data[k]);

    this._hass.callService("deskdot", "card", data);
    this._showForm = false;
    this._editing = null;
    this._render();
  }
}

customElements.define("deskdot-card", DeskDotCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "custom:deskdot-card",
  name: "DeskDot Card Manager",
  description: "View, create, edit and delete cards on a DeskDot display",
  preview: false,
});

console.info("%c DESKDOT-CARD %c v0.1.5 ", "color:#fff;background:#00aaff;padding:2px 6px;border-radius:3px", "");

class AldesPlanningCard extends HTMLElement {
    _initPlanningGrid(planning) {
        // Initialise le tableau local à partir du planning
        const grid = Array(7).fill().map(() => Array(24).fill('C'));
        planning.forEach(p => {
            const command = typeof p === 'string' ? p : p?.command;
            if (command && command.length >= 3) {
                const hour = this.decodeHour(command[0]);
                const day = parseInt(command[1], 10);
                const mode = command[2];
                if (!isNaN(day) && hour !== null) {
                    grid[day][hour] = mode;
                }
            }
        });
        return grid;
    }

    decodeHour(hChar) {
        if (hChar >= '0' && hChar <= '9') return parseInt(hChar, 10);
        const map = {
            'A': 10, 'B': 11, 'C': 12, 'D': 13,
            'E': 14, 'F': 15, 'G': 16, 'H': 17,
            'I': 18, 'J': 19, 'K': 20, 'L': 21,
            'M': 22, 'N': 23,
        };
        return map[hChar] ?? null;
    }

    _planningGridToString(grid) {
        let str = '';
        for (let day = 0; day < 7; day++) {
            for (let hour = 0; hour < 24; hour++) {
                let hChar = hour < 10 ? String(hour) : String.fromCharCode(55 + hour); // 10->A, 11->B, ...
                str += `${hChar}${day}${grid[day][hour]}`;
            }
        }
        return str;
    }
    constructor() {
        super();
        this._hass = null;
        this._config = null;
        this._planningGrids = {}; // per-entity grid
        this._pendingListeners = [];
        this._statusByEntity = {};
        this._selectedEntityId = null;
    }

    setConfig(config) {
        this._config = config;
    }

    set hass(hass) {
        const oldHass = this._hass;
        this._hass = hass;

        // Only re-render if hass actually changed
        if (!oldHass || this._hasChanged(oldHass, hass)) {
            this.render();
        }
    }

    _hasChanged(oldHass, newHass) {
        if (!oldHass) return true;

        const entities = this._config?.entities || [this._config?.entity];
        const validEntities = entities.filter(e => e);

        // Check if any entity state changed
        return validEntities.some(entityId => {
            const oldState = oldHass.states[entityId];
            const newState = newHass.states[entityId];
            return oldState !== newState;
        });
    }

    render() {
        if (!this._hass || !this._config) return;

        // Support multiple entity configurations; fallback to auto-discovery if none provided
        const entities = this._config?.entities || [this._config?.entity];
        const baseEntities = (entities || []).filter(Boolean);
        const discovered = baseEntities.length === 0 ? this._discoverEntities() : baseEntities;

        const validEntities = (discovered || [])
            .map((e) => this._resolveEntityId(e))
            .filter((e) => e)
            .sort((a, b) => {
                const ra = this._modeRank(a);
                const rb = this._modeRank(b);
                if (ra !== rb) return ra - rb;
                return (a || '').localeCompare(b || '');
            });

        if (validEntities.length === 0) {
            this.innerHTML = '<div style="color: red; padding: 16px;">No entities configured</div>';
            return;
        }

        this._pendingListeners = [];
        let html = '<div style="padding: 16px;">';

        // Build meta list
        const metas = validEntities.map((entityId) => {
            const entity = this._hass?.states[entityId];
            return { entityId, entity };
        }).filter(m => m.entity);

        if (metas.length === 0) {
            this.innerHTML = '<div style="color: red; padding: 16px;">No entities found</div>';
            return;
        }

        // Select current entity
        if (!this._selectedEntityId || !metas.find(m => m.entityId === this._selectedEntityId)) {
            this._selectedEntityId = metas[0].entityId;
        }

        if (metas.length > 1) {
            html += '<div style="margin-bottom: 12px; display:flex; align-items:center; gap:8px;">';
            html += '<label style="font-weight:600;">Programme :</label>';
            html += `<select id="planning-entity-select" style="padding:6px 8px; font-size:14px;">`;
            for (const meta of metas) {
                const friendlyName = meta.entity.attributes?.friendly_name || meta.entityId;
                const selected = meta.entityId === this._selectedEntityId ? 'selected' : '';
                html += `<option value="${meta.entityId}" ${selected}>${friendlyName}</option>`;
            }
            html += '</select></div>';
        }

        const selectedMeta = metas.find(m => m.entityId === this._selectedEntityId) || metas[0];
        const entity = selectedMeta.entity;
        const entityId = selectedMeta.entityId;
        const planning = entity.attributes?.planning_data || [];
        if (!Array.isArray(planning) || planning.length === 0) {
            html += `<div style="color: orange; margin-bottom: 16px;">No planning data for ${entityId}</div>`;
        } else {
            const friendlyName = entity.attributes?.friendly_name || entityId;
            const icon = entity.attributes?.icon || '📅';
            const grid = this._planningGrids[entityId] ?? this._initPlanningGrid(planning);
            this._planningGrids[entityId] = grid;
            const slug = entityId.toLowerCase().replace(/[^a-z0-9]+/g, '-');
            this._statusByEntity[entityId] ||= { loading: false, message: '', ok: true };
            html += this.renderPlanningSection(friendlyName, icon, slug, entityId, grid);
            this._pendingListeners.push({ slug, entityId, grid, title: friendlyName });
        }

        html += '</div>';
        this.innerHTML = html;

        // Ajout des listeners (édition + clic grille) par entité
        const selectEl = this.querySelector('#planning-entity-select');
        if (selectEl) {
            selectEl.onchange = (e) => {
                this._selectedEntityId = e.target.value;
                this.render();
            };
        }

        for (const meta of this._pendingListeners) {
            const { slug, entityId, grid, title } = meta;
            const sendBtn = this.querySelector(`#send-planning-btn-${slug}`);
            const statusEl = this.querySelector(`#status-${slug}`);
            const inferredMode = this._inferMode(entityId, title);
            if (sendBtn) {
                sendBtn.onclick = async () => {
                    const newPlanning = this._planningGridToString(grid);
                    const mode = inferredMode;
                    this._statusByEntity[entityId] = { loading: true, message: '', ok: true };
                    if (statusEl) {
                        statusEl.style.color = this._getHaTheme().cellText;
                        statusEl.textContent = 'Envoi...';
                    }
                    sendBtn.disabled = true;
                    sendBtn.textContent = 'Envoi...';
                    try {
                        const timeout = new Promise((_, reject) => setTimeout(() => reject(new Error('timeout')), 12000));
                        await Promise.race([
                            this._hass.callService('aldes', 'set_week_planning', {
                                entity_id: entityId,
                                planning: newPlanning,
                                mode,
                            }),
                            timeout,
                        ]);
                        this._statusByEntity[entityId] = { loading: false, message: 'Planning modifié', ok: true };
                        if (statusEl) {
                            statusEl.style.color = 'var(--success-color, #28a745)';
                            statusEl.textContent = 'Planning modifié';
                        }
                    } catch (e) {
                        this._statusByEntity[entityId] = { loading: false, message: 'Erreur lors de l\'envoi', ok: false };
                        if (statusEl) {
                            statusEl.style.color = 'var(--error-color, #d32f2f)';
                            statusEl.textContent = 'Erreur lors de l\'envoi';
                        }
                    } finally {
                        sendBtn.disabled = false;
                        sendBtn.textContent = 'Modifier le planning';
                    }
                };
            }
            // Clic sur chaque case
            for (let day = 0; day < 7; day++) {
                for (let hour = 0; hour < 24; hour++) {
                    const cell = this.querySelector(`[data-entity="${entityId}"][data-day="${day}"][data-hour="${hour}"]`);
                    if (!cell) continue;
                    cell.onclick = () => {
                        const current = grid[day][hour];
                        const next = current === 'B' ? 'C' : 'B';
                        grid[day][hour] = next;
                        this._planningGrids[entityId] = grid;
                        this.render();
                    };
                }
            }
        }
    }

    renderPlanningSection(title, icon, slug, entityId, grid) {
        const days = ['Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam', 'Dim'];
        const displayIcon = (icon || '').startsWith('mdi:')
            ? `<ha-icon icon="${icon}" style="--mdc-icon-size:20px; vertical-align: middle;"></ha-icon>`
            : (icon || '');

        const lowerTitle = title.toLowerCase();

        // Determine if this is heating or cooling program based on title
        const isHeating = lowerTitle.includes('chauffage');
        const isCooling = lowerTitle.includes('climatisation');

        // Mode names depend on program type
        let modeNames, modeColors;

        if (isHeating) {
            // Heating: B=Confort, C=Eco (inversion demandée)
            modeNames = {
                'B': 'Confort',
                'C': 'Eco',
            };
            modeColors = {
                'B': '#FF6B6B', // Rouge - Confort
                'C': '#FFA500', // Orange - Eco
            };
        } else if (isCooling) {
            // Cooling: C=Off, B=Confort (codes B/C uniquement)
            modeNames = {
                'C': 'Off',
                'B': 'Confort',
            };
            modeColors = {
                'C': '#808080', // Gris - Off
                'B': '#4169E1', // Bleu - Confort
            };
        }

        // Theme-aware palette based on Home Assistant CSS vars
        const theme = this._getHaTheme();

        const status = this._statusByEntity?.[entityId] || { loading: false, message: '', ok: true };
        const statusColor = status.ok ? 'var(--success-color, #28a745)' : 'var(--error-color, #d32f2f)';
        const buttonLabel = status.loading ? 'Envoi...' : 'Modifier le planning';

        let html = `
            <div style="margin-bottom: 32px; background:${theme.cardBg}; border-radius:8px; padding:12px; border:1px solid ${theme.border};">
                <div style="font-size: 18px; font-weight: bold; margin-bottom: 16px; padding-bottom: 8px; border-bottom: 2px solid ${theme.border}; color:${theme.cellText}; display:flex; align-items:center; gap:8px;">
                    ${displayIcon ? `${displayIcon}` : ''}
                    <span>${title}</span>
                </div>
                <div style="overflow-x: auto;">
                    <div style="display: grid; grid-template-columns: 60px repeat(7, 1fr); gap: 2px; background: ${theme.gridBg}; padding: 2px; min-width: min-content;">
                        <div style="padding: 8px; font-weight: bold; background: ${theme.headerBg}; text-align: center; color:${theme.cellText};">Time</div>
        `;

        // Day headers
        for (let day = 0; day < 7; day++) {
            html += `<div style="padding: 8px; font-weight: bold; background: ${theme.headerBg}; text-align: center; color:${theme.cellText};">${days[day]}</div>`;
        }
        for (let hour = 0; hour < 24; hour++) {
            html += `<div style="padding: 8px; font-weight: bold; background: ${theme.headerBg}; text-align: center; font-size: 12px; color:${theme.cellText};">${hour.toString().padStart(2, '0')}h</div>`;
            for (let day = 0; day < 7; day++) {
                const mode = grid[day][hour];
                let color, modeName;
                if (title.toLowerCase().includes('chauffage')) {
                    color = { 'B': '#ff6b6b', 'C': '#ffa500' }[mode] || '#CCCCCC';
                    modeName = { 'B': 'Confort', 'C': 'Eco' }[mode] || 'Unknown';
                } else if (title.toLowerCase().includes('climatisation')) {
                    color = { 'B': '#4a7dff', 'C': '#6f737a' }[mode] || '#CCCCCC';
                    modeName = { 'B': 'Confort', 'C': 'Off' }[mode] || 'Unknown';
                }
                html += `
                  <div style="
                    padding: 8px;
                    background: ${color};
                    color: #ffffff;
                    text-align: center;
                    cursor: pointer;
                    font-size: 12px;
                    font-weight: bold;
                    border-radius: 4px;
                    user-select: none;
                    transition: opacity 0.2s;
                  "
                  data-entity="${entityId}" data-day="${day}" data-hour="${hour}"
                  title="${days[day]} ${hour.toString().padStart(2, '0')}h: ${modeName}"
                                    >&nbsp;</div>
                `;
            }
        }

        html += `
                  </div>
                </div>
                <div style="margin-top: 12px; padding: 12px; background: ${theme.headerBg}; border-radius: 4px; font-size: 12px; color:${theme.cellText};">
            <div style="font-weight: bold; margin-bottom: 8px;">Modes:</div>
        `;

        for (const [mode, name] of Object.entries(modeNames)) {
            html += `<div style="margin: 4px 0; display: flex; align-items: center; gap: 8px; color:${theme.cellText};">
                            <div style="width: 20px; height: 20px; background: ${modeColors[mode]}; border-radius: 3px;"></div>
                            <span>${name}</span>
            </div>`;
        }

        html += `
        </div>
        <div style="margin-top:16px; display:flex; align-items:center; gap:12px;">
            <button id="send-planning-btn-${slug}" style="padding:8px 16px; font-size:14px;" ${status.loading ? 'disabled' : ''}>${buttonLabel}</button>
            <span id="status-${slug}" style="font-size:12px; min-height:18px; color:${status.message ? statusColor : theme.cellText};">${status.message || ''}</span>
        </div>
      </div>
    `;

        return html;
    }

    getCardSize() {
        return 4;
    }

    _resolveEntityId(entityId) {
        if (!entityId) return null;
        // If entity exists as-is, keep it
        if (this._hass?.states?.[entityId]) return entityId;

        // If a sensor planning entity is configured, map to the text equivalent when present
        const match = entityId.match(/^sensor\.aldes_(.*_planning_(heating|cooling)_prog_[a-d])$/i);
        if (match) {
            const suffix = match[1];
            const textId = `text.aldes_${suffix}`;
            if (this._hass?.states?.[textId]) return textId;

            // Fallback: try to find any text entity matching the suffix (helps if user removed sensors and only text remains)
            const candidate = Object.keys(this._hass?.states || {}).find((key) =>
                key.startsWith('text.aldes_') && key.endsWith(suffix)
            );
            if (candidate) return candidate;
        }

        // Fallback: return original (will show not found)
        return entityId;
    }

    _discoverEntities() {
        const ids = Object.keys(this._hass?.states || {});
        const regex = /^sensor\.aldes_.*_planning_(heating|cooling)_prog_[a-d]$/i;
        return ids.filter((id) => regex.test(id)).sort();
    }

    _modeRank(entityId) {
        const match = (entityId || '').match(/prog_([a-d])/i);
        if (!match) return 99;
        const letter = match[1].toLowerCase();
        const order = { a: 0, b: 1, c: 2, d: 3 };
        return order[letter] ?? 99;
    }

    _inferMode(entityId, title) {
        const idMatch = (entityId || '').match(/prog_([a-d])/i);
        if (idMatch) return idMatch[1].toUpperCase();
        const match = (title || '').match(/\b([A-D])\b/i);
        if (match) return match[1].toUpperCase();
        const lower = (title || '').toLowerCase();
        if (lower.includes('planning a') || lower.includes('programme a')) return 'A';
        if (lower.includes('planning b') || lower.includes('programme b')) return 'B';
        if (lower.includes('planning c') || lower.includes('programme c')) return 'C';
        if (lower.includes('planning d') || lower.includes('programme d')) return 'D';
        return 'A';
    }

    _getHaTheme() {
        const css = getComputedStyle(document.documentElement);
        const cardBg = (css.getPropertyValue('--card-background-color') || '').trim() || '#ffffff';
        let headerBg = (css.getPropertyValue('--secondary-background-color') || '').trim() || '#f7f7f7';
        let gridBg = (css.getPropertyValue('--divider-color') || '').trim() || '#f7f7f7';
        const border = (css.getPropertyValue('--divider-color') || '').trim() || '#ededed';
        const cellText = (css.getPropertyValue('--primary-text-color') || '').trim() || '#222222';

        const normalize = (c) => (c || '').replace(/\s+/g, '').toLowerCase();
        if (normalize(headerBg) === '#e5e5e5') headerBg = '#f9f9f9';
        if (normalize(gridBg) === '#e5e5e5') gridBg = '#f9f9f9';

        return { cardBg, headerBg, gridBg, border, cellText };
    }
}

// Register the custom element
if (!customElements.get('aldes-planning-card')) {
    customElements.define('aldes-planning-card', AldesPlanningCard);
    console.log('Aldes Planning Card registered successfully');
} else {
    console.log('Aldes Planning Card already registered');
}

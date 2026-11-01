/**
 * Main Application Controller for DevLabs • HarnessAgents v4.0.5
 * Connects the Isometric 2.5D Virtual Office, Right Inspector, Bottom Agent Roster,
 * Split Multi-Terminal Matrix, Kanban Board, and 311 ECC Skill Armory.
 */

class HarnessOfficeApp {
  constructor() {
    this.state = null;
    this.allSkills = [];
    this.selectedAgentId = 'ramon';
    this.activeInspectorTab = 'terminal';
    this.activeStageView = 'office';
    this.inspectorCache = {};
    this.termFontSize = 12;

    this.officeCanvas = new window.IsometricOfficeEngine('officeCanvas');
    window.officeCanvas = this.officeCanvas;
  }

  async init() {
    await this.refreshState();
    await this.loadECCSkillsCatalog();
    await this.selectAgent(this.selectedAgentId);
    this._connectWebSocket();
    // Sync bottom roster & inspector status badges every 500ms with live canvas work state
    setInterval(() => this._syncLiveWorkingBadges(), 500);
  }

  isAgentVisuallyWorking(agent) {
    if (!agent) return false;
    if (agent.status === 'working') return true;
    if (this.officeCanvas && this.officeCanvas.isAgentInWorkMode) {
      return this.officeCanvas.isAgentInWorkMode(agent);
    }
    return false;
  }

  _syncLiveWorkingBadges() {
    if (!this.state) return;
    const agents = this.state.agents || [];
    this._renderBottomRoster(agents);
    const selAgent = agents.find((a) => a.id === this.selectedAgentId);
    if (selAgent) {
      const isWork = this.isAgentVisuallyWorking(selAgent);
      const pill = document.getElementById('inspStatusPill');
      if (pill) {
        pill.textContent = isWork ? '⚡ working' : `▪ ${selAgent.status}`;
        pill.className = `status-pill ${isWork ? 'working' : ''}`;
      }
    }
  }

  async refreshState() {
    const resp = await fetch('/api/state');
    this.state = await resp.json();
    this._renderAll();
  }

  async loadECCSkillsCatalog(query = '') {
    const url = query ? `/api/skills?q=${encodeURIComponent(query)}` : '/api/skills';
    const resp = await fetch(url);
    const data = await resp.json();
    this.allSkills = data.skills || [];
    const total = (data.stats && data.stats.total_skills) || this.allSkills.length;
    const subCount = (data.stats && data.stats.total_subagents) || 71;
    document.getElementById('eccBadgeCount').textContent = `• ${total} ECC Skills (${subCount} Subagents)`;
    document.getElementById('eccCatalogHeader').textContent =
      `🎒 Downloaded ECC Armory Catalog (${total} Skills & ${subCount} Subagents Ready)`;
    this._renderECCSkillGrid();
  }

  _connectWebSocket() {
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const ws = new WebSocket(`${proto}//${window.location.host}/ws`);
    ws.onmessage = (evt) => {
      try {
        const msg = JSON.parse(evt.data);
        if (msg.type === 'initial_state' && msg.payload) {
          this.state = msg.payload;
          this._renderAll();
        }
      } catch (_) {
        // Ignore malformed packets
      }
    };
  }

  _renderAll() {
    if (!this.state) return;
    const agents = this.state.agents || [];
    const activeFloor = this.state.active_floor || 1;

    // Sync Isometric Canvas
    this.officeCanvas.syncState(
      agents,
      this.state.furniture || [],
      activeFloor,
      this.selectedAgentId,
      this.state.floor_tiles || {}
    );

    // Top Auto-Mode Button
    const autoBtn = document.getElementById('autoModeBtn');
    autoBtn.textContent = this.state.auto_mode ? 'auto mode on' : 'auto mode off';
    autoBtn.className = `auto-mode-btn ${this.state.auto_mode ? '' : 'off'}`;

    // Top-Center Floor Header & Agent Initials
    document.getElementById('floorHeaderLabel').textContent = `─── FLOOR ${activeFloor} ───`;
    const floorAgents = agents.filter((a) => a.floor === activeFloor);
    document.getElementById('agentsCountLabel').textContent = `👥 ${floorAgents.length} AGENTS`;
    const dotsEl = document.getElementById('miniInitialDots');
    dotsEl.innerHTML = floorAgents
      .map((a) => `<div class="mini-dot" style="background:${a.avatar_color}" title="${a.name}">${a.name[0].toUpperCase()}</div>`)
      .join('');

    // Bottom-Center Floor Buttons
    const floorBtns = document.getElementById('floorButtonsContainer');
    floorBtns.innerHTML = (this.state.floors || [])
      .map((f) => {
        const count = agents.filter((a) => a.floor === f.floor_number).length;
        const activeCls = f.floor_number === activeFloor ? 'active' : '';
        return `<button class="floor-btn ${activeCls}" onclick="window.app.switchFloor(${f.floor_number})">Floor ${f.floor_number}<br/>• ${count}/${f.max_agents}</button>`;
      })
      .join('');

    // Populate Model Selects
    const modelOptionsHtml = (this.state.models || [])
      .map((m) => `<option value="${m.id}">${m.label} [${m.speed_label}]</option>`)
      .join('');
    const inspModelSel = document.getElementById('inspModelSelect');
    if (inspModelSel && inspModelSel.innerHTML !== modelOptionsHtml) {
      inspModelSel.innerHTML = modelOptionsHtml;
      document.getElementById('newAgentModel').innerHTML = modelOptionsHtml;
    }

    // Bottom Roster Cards
    this._renderBottomRoster(agents);

    // Right Inspector for Selected Agent
    this._renderRightInspector();

    // Alternate Views if open
    this._renderTopologyView(agents);
    this._renderSplitTerminalsView(agents);
    this._renderKanbanBoard();
  }

  _renderBottomRoster(agents) {
    const dock = document.getElementById('bottomRosterDock');
    const cardsHtml = agents
      .map((a) => {
        const sel = a.id === this.selectedAgentId ? 'selected' : '';
        const isWorking = this.isAgentVisuallyWorking(a);
        const workCls = isWorking ? 'working-card' : '';
        const statusColor = isWorking ? '#fde047' : '#a3e635';
        const statusLabel = isWorking ? '⚡ working' : `▪ ${a.status}`;
        return `
          <div class="roster-card ${sel} ${workCls}" onclick="window.app.selectAgent('${a.id}')">
            <div class="roster-avatar" style="border-color:${a.avatar_color}">
              <span style="font-size:22px;">${a.is_hive_lead ? '🧠' : '🧑‍💻'}</span>
            </div>
            <div class="roster-info">
              <div class="roster-top-line">
                <span>${a.name}</span>
                <span style="color:${statusColor};font-size:10px;font-weight:700;">${statusLabel}</span>
              </div>
              <div class="roster-dept" title="${a.department}">${a.department}</div>
              <div class="roster-talk-row">
                <span class="talk-pill">💬 talk</span>
                <span style="font-size:9px;color:#9ca3af;">${a.model_id.split('-')[0]}</span>
              </div>
            </div>
          </div>
        `;
      })
      .join('');

    dock.innerHTML = `${cardsHtml}<button class="add-agent-btn" onclick="window.app.openAddAgentModal()">+ add agent</button>`;
  }

  async selectAgent(agentId) {
    this.selectedAgentId = agentId;
    const resp = await fetch(`/api/agents/${encodeURIComponent(agentId)}/inspector`);
    if (resp.ok) {
      this.inspectorCache[agentId] = await resp.json();
    }
    this._renderAll();
  }

  _renderRightInspector() {
    if (!this.state) return;
    const agent = (this.state.agents || []).find((a) => a.id === this.selectedAgentId);
    if (!agent) return;

    const isWork = this.isAgentVisuallyWorking(agent);
    document.getElementById('inspAgentTitle').textContent = agent.display_title;
    const inspPill = document.getElementById('inspStatusPill');
    inspPill.textContent = isWork ? '⚡ working' : `▪ ${agent.status}`;
    inspPill.className = `status-pill ${isWork ? 'working' : ''}`;
    const wpEl = document.getElementById('inspWorkspacePath');
    if (wpEl) {
      wpEl.textContent = `📂 ${agent.workspace_path}`;
      wpEl.title = `Click to open ${agent.workspace_path} in Windows Explorer`;
    }
    document.getElementById('inspPtyId').textContent = `▪ live · pty ${agent.pty_id}`;
    document.getElementById('moveAgentLabel').textContent = `MOVE ${agent.name.toUpperCase()} TO`;
    document.getElementById('moveFloorSelect').value = String(agent.floor);

    const modelSel = document.getElementById('inspModelSelect');
    if (modelSel) modelSel.value = agent.model_id;

    // Equipped ECC Skills Chips
    const skillsContainer = document.getElementById('inspSkillsList');
    skillsContainer.innerHTML = (agent.equipped_skills || [])
      .map(
        (sk) => `
        <span class="skill-chip">
          ⚡ ${sk}
          <button onclick="window.app.unequipSkill('${sk}')" title="Unequip skill">×</button>
        </span>
      `
      )
      .join('');

    // Guardrail Buttons
    const blockBtn = document.getElementById('blockToolsBtn');
    blockBtn.style.borderColor = agent.block_tools ? '#ef4444' : '#3f3f46';
    blockBtn.style.color = agent.block_tools ? '#fca5a5' : '#e4e4e7';
    blockBtn.textContent = agent.block_tools ? '🚫 tools blocked' : 'block tools';

    // Harness Level Selector (off | lite | [ full ] | ultra)
    document.querySelectorAll('.lvl-btn').forEach((btn) => {
      const lvl = btn.getAttribute('data-lvl');
      const isAct = lvl === agent.harness_level;
      btn.className = `lvl-btn ${isAct ? 'active' : ''}`;
      btn.textContent = isAct ? `[ ${lvl} ]` : lvl;
    });

    // Mascot Header & Telemetry
    document.getElementById('mascotEngineTitle').textContent = `HarnessAgents • ${agent.name.toUpperCase()}`;
    document.getElementById('mascotModelLine').textContent = `${agent.model_id} (${agent.provider}) • ${agent.equipped_skills.length} ECC Skills`;
    document.getElementById('mascotFolderLine').textContent = agent.workspace_path;

    const tele = agent.telemetry || {};
    document.getElementById('teleCost').textContent = `$${(tele.cost_usd || 0).toFixed(2)}`;
    document.getElementById('teleTokens').textContent = `${(tele.tokens_in || 0) + (tele.tokens_out || 0)}`;
    document.getElementById('teleTurns').textContent = `${tele.tokens_out || 0} out • ${tele.turns || 0} turns`;
    document.getElementById('teleTime').textContent = `${tele.agent_time_sec || 0}s`;
    const ctxPct = Math.round(((tele.context_used_tokens || 8000) / (tele.context_max_tokens || 1000000)) * 100);
    document.getElementById('teleCtxLine').textContent =
      `ctx ${Math.round((tele.context_used_tokens || 8000) / 1000)}k/${Math.round((tele.context_max_tokens || 1000000) / 1000)}k (${ctxPct}%)`;

    document.getElementById('queueCountLabel').textContent = `queue (${(agent.prompt_queue || []).length})`;
    document.getElementById('promptInputBox').placeholder = `Message ${agent.display_title}...`;

    // Render Active Inspector Tab Body
    const cached = this.inspectorCache[agent.id] || {};
    const pre = document.getElementById('terminalOutputPre');
    pre.style.fontSize = `${this.termFontSize}px`;

    if (this.activeInspectorTab === 'terminal') {
      const lines = cached.terminal_logs || [];
      pre.textContent = this._stripAnsi(lines.join('\n'));
    } else if (this.activeInspectorTab === 'git') {
      pre.textContent = cached.git_info || 'Loading git status & diff...';
    } else if (this.activeInspectorTab === 'messages') {
      const msgs = cached.messages || [];
      pre.textContent = msgs
        .map((m) => `[${m.channel.toUpperCase()}] ${m.sender_id} -> ${m.recipient_id}: ${m.content}`)
        .join('\n\n') || 'No inter-agent messages yet.';
    } else if (this.activeInspectorTab === 'traces') {
      const tr = cached.traces || [];
      pre.textContent = tr
        .map((t) => `[${t.timestamp.slice(11, 19)}] ${t.event}: ${t.detail}`)
        .join('\n') || 'No traces recorded.';
    }

    const vp = document.getElementById('inspectorViewport');
    vp.scrollTop = vp.scrollHeight;
  }

  _stripAnsi(str) {
    return (str || '').replace(/\x1b\[[0-9;]*m/g, '');
  }

  switchStageView(viewName) {
    this.activeStageView = viewName;
    document.querySelectorAll('.view-tab').forEach((btn) => {
      btn.classList.toggle('active', btn.getAttribute('data-view') === viewName);
    });
    document.getElementById('stageViewGraph').classList.toggle('active', viewName === 'graph');
    document.getElementById('stageViewSplit').classList.toggle('active', viewName === 'split');
    document.getElementById('stageViewKanban').classList.toggle('active', viewName === 'kanban');
    if (viewName === 'split') {
      this._loadAllTerminalCaches();
    }
  }

  async _loadAllTerminalCaches() {
    if (!this.state) return;
    for (const a of this.state.agents || []) {
      const r = await fetch(`/api/agents/${encodeURIComponent(a.id)}/inspector`);
      if (r.ok) this.inspectorCache[a.id] = await r.json();
    }
    this._renderSplitTerminalsView(this.state.agents || []);
  }

  _renderTopologyView(agents) {
    const el = document.getElementById('topologyCardsContainer');
    if (!el) return;
    el.innerHTML = agents
      .map(
        (a) => `
        <div class="kanban-card" style="border-color:${a.avatar_color};padding:14px;">
          <div style="display:flex;justify-content:space-between;align-items:center;">
            <strong style="font-size:14px;">${a.is_hive_lead ? '🧠' : '⚡'} ${a.display_title}</strong>
            <span class="status-pill">${a.status}</span>
          </div>
          <div style="font-size:11px;color:#9ca3af;margin:6px 0;font-family:var(--font-mono);">
            Model: <strong style="color:#fff;">${a.model_id}</strong> (${a.provider})
          </div>
          <div style="font-size:11px;margin-bottom:8px;">
            Equipped ECC Skills: ${(a.equipped_skills || []).map((s) => `<span class="skill-chip" style="display:inline-flex;margin:2px;">${s}</span>`).join('')}
          </div>
          <div style="display:flex;gap:6px;">
            <button class="sm-btn" onclick="window.app.selectAgent('${a.id}');window.app.switchStageView('office')">Inspect in Office</button>
            <button class="sm-btn" onclick="window.app.quickHandoffTo('${a.id}')">💬 Send 1:1 Handoff</button>
          </div>
        </div>
      `
      )
      .join('');
  }

  _renderSplitTerminalsView(agents) {
    const grid = document.getElementById('splitTerminalsGrid');
    if (!grid) return;
    grid.innerHTML = agents
      .slice(0, 6)
      .map((a) => {
        const logs = (this.inspectorCache[a.id] && this.inspectorCache[a.id].terminal_logs) || [
          `● ${a.pty_id} (${a.model_id})`,
          `Skills: ${(a.equipped_skills || []).join(', ')}`,
          `> Ready in ${a.workspace_path}`,
        ];
        return `
          <div class="mini-term-card">
            <div class="mini-term-header" style="border-left:3px solid ${a.avatar_color}">
              <span>${a.name.toUpperCase()} • ${a.model_id}</span>
              <span style="color:#a3e635;">${a.status}</span>
            </div>
            <div class="mini-term-body">${this._stripAnsi(logs.slice(-14).join('\n'))}</div>
          </div>
        `;
      })
      .join('');
  }

  _renderKanbanBoard() {
    if (!this.state) return;
    const container = document.getElementById('kanbanBoardContainer');
    if (!container) return;
    const tasks = this.state.kanban || [];
    const cols = [
      { key: 'backlog', label: 'Backlog' },
      { key: 'in_progress', label: 'In Progress' },
      { key: 'review', label: 'Review / Sec Gate' },
      { key: 'done', label: 'Done ✓' },
    ];

    container.innerHTML = cols
      .map((c) => {
        const colTasks = tasks.filter((t) => t.status === c.key);
        const cards = colTasks
          .map(
            (t) => `
            <div class="kanban-card">
              <div class="kanban-card-title">#${t.id} ${t.title}</div>
              <div style="font-size:11px;color:#9ca3af;">${t.description}</div>
              <div style="margin-top:5px;">
                ${(t.recommended_skills || []).map((s) => `<span class="skill-chip" style="display:inline-flex;margin-right:3px;">${s}</span>`).join('')}
              </div>
              <div class="kanban-card-meta">
                <span>👤 ${t.assigned_agent_id || 'unassigned'}</span>
                <div style="display:flex;gap:4px;">
                  ${c.key !== 'done' ? `<button class="sm-btn" onclick="window.app.advanceTask(${t.id}, '${c.key}')">Next →</button>` : ''}
                </div>
              </div>
            </div>
          `
          )
          .join('');
        return `<div class="kanban-col"><h4><span>${c.label}</span><span>${colTasks.length}</span></h4>${cards}</div>`;
      })
      .join('');
  }

  _renderECCSkillGrid() {
    const grid = document.getElementById('eccSkillGrid');
    if (!grid) return;
    const agent = (this.state && (this.state.agents || []).find((a) => a.id === this.selectedAgentId)) || null;
    const equippedSet = new Set((agent && agent.equipped_skills) || []);

    grid.innerHTML = this.allSkills
      .slice(0, 90)
      .map((sk) => {
        const isEq = equippedSet.has(sk.id);
        return `
          <div class="ecc-skill-item">
            <div>
              <div style="display:flex;justify-content:space-between;align-items:center;">
                <strong style="font-size:12px;color:#f4f4f5;">${sk.id}</strong>
                <span style="font-size:9px;color:#67e8f9;font-family:var(--font-mono);">${sk.category}</span>
              </div>
              <div style="font-size:11px;color:#9ca3af;margin-top:4px;">${sk.description}</div>
            </div>
            <button class="sm-btn" style="align-self:flex-end;border-color:${isEq ? '#a3e635' : '#38bdf8'};color:${isEq ? '#a3e635' : '#67e8f9'};"
              onclick="window.app.${isEq ? 'unequipSkill' : 'equipSkill'}('${sk.id}')">
              ${isEq ? '✓ Equipped' : '+ Equip to ' + (agent ? agent.name : 'Agent')}
            </button>
          </div>
        `;
      })
      .join('');
  }

  filterECCSkills(q) {
    this.loadECCSkillsCatalog(q);
  }

  async equipSkill(skillId) {
    await fetch(`/api/agents/${encodeURIComponent(this.selectedAgentId)}/skills/equip`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ skill_id: skillId }),
    });
    await this.refreshState();
    await this.selectAgent(this.selectedAgentId);
    this._renderECCSkillGrid();
  }

  async unequipSkill(skillId) {
    await fetch(`/api/agents/${encodeURIComponent(this.selectedAgentId)}/skills/unequip`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ skill_id: skillId }),
    });
    await this.refreshState();
    await this.selectAgent(this.selectedAgentId);
    this._renderECCSkillGrid();
  }

  async sendPromptFromBox(queueOnly = false) {
    const box = document.getElementById('promptInputBox');
    const text = box.value.trim();
    if (!text) return;
    box.value = '';

    if (!queueOnly && this.officeCanvas) {
      this.officeCanvas.markAgentWorking(this.selectedAgentId, 1100);
      if (this.selectedAgentId === 'ramon') {
        ['ada', 'ken', 'mira', 'sentinel'].forEach((id) =>
          this.officeCanvas.markAgentWorking(id, 1100)
        );
      }
    }

    await fetch(`/api/agents/${encodeURIComponent(this.selectedAgentId)}/prompt`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt: text, is_steer: false, queue_only: queueOnly }),
    });
    await this.refreshState();
    await this.selectAgent(this.selectedAgentId);
  }

  async steerSelectedAgent() {
    const inp = document.getElementById('steerNoteInput');
    const note = inp.value.trim();
    if (!note) return;
    inp.value = '';

    await fetch(`/api/agents/${encodeURIComponent(this.selectedAgentId)}/prompt`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt: note, is_steer: true, queue_only: false }),
    });
    await this.refreshState();
    await this.selectAgent(this.selectedAgentId);
  }

  async changeAgentModel(modelId) {
    await fetch(`/api/agents/${encodeURIComponent(this.selectedAgentId)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model_id: modelId }),
    });
    await this.refreshState();
    await this.selectAgent(this.selectedAgentId);
  }

  async setHarnessLevel(level) {
    await fetch(`/api/agents/${encodeURIComponent(this.selectedAgentId)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ harness_level: level }),
    });
    await this.refreshState();
    await this.selectAgent(this.selectedAgentId);
  }

  async toggleBlockTools() {
    const agent = (this.state.agents || []).find((a) => a.id === this.selectedAgentId);
    if (!agent) return;
    await fetch(`/api/agents/${encodeURIComponent(this.selectedAgentId)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ block_tools: !agent.block_tools }),
    });
    await this.refreshState();
  }

  async toggleStopAfterStep() {
    const agent = (this.state.agents || []).find((a) => a.id === this.selectedAgentId);
    if (!agent) return;
    await fetch(`/api/agents/${encodeURIComponent(this.selectedAgentId)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ stop_after_step: !agent.stop_after_step }),
    });
    await this.refreshState();
  }

  async runMacro(macroName) {
    const resp = await fetch(
      `/api/agents/${encodeURIComponent(this.selectedAgentId)}/macros/${encodeURIComponent(macroName)}`,
      { method: 'POST' }
    );
    const data = await resp.json();
    if (macroName === 'copy' && data.clipboard_text && navigator.clipboard) {
      navigator.clipboard.writeText(data.clipboard_text).catch(() => {});
    }
    await this.refreshState();
    await this.selectAgent(this.selectedAgentId);
  }

  async toggleAutoMode() {
    await fetch('/api/auto-mode', { method: 'POST' });
    await this.refreshState();
    await this.selectAgent(this.selectedAgentId);
  }

  async triggerSweldo() {
    await fetch('/api/celebrate?message=' + encodeURIComponent('SWELDO NA! 🎉'), { method: 'POST' });
    await this.refreshState();
  }

  async walkSelectedAgentTo(gx, gy) {
    const agent = (this.state.agents || []).find((a) => a.id === this.selectedAgentId);
    if (!agent) return;
    const localAgent = this.officeCanvas.agents.find((a) => a.id === this.selectedAgentId);
    if (localAgent && this.officeCanvas._assignAgentPathTo) {
      this.officeCanvas._assignAgentPathTo(localAgent, gx, gy);
    }
    await fetch(`/api/agents/${encodeURIComponent(this.selectedAgentId)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ target_x: gx, target_y: gy }),
    });
  }

  async open1to1Prompt() {
    const peers = (this.state.agents || []).filter((a) => a.id !== this.selectedAgentId);
    const target = peers[0] ? peers[0].id : 'ada';
    this.quickHandoffTo(target);
  }

  async quickHandoffTo(recipientId) {
    const msg = `Syncing API & UI contract with @${recipientId} (311 ECC Harness active)`;
    await fetch('/api/messages', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        sender_id: this.selectedAgentId,
        recipient_id: recipientId,
        content: msg,
        channel: '1:1',
      }),
    });
    await this.refreshState();
    await this.selectAgent(this.selectedAgentId);
  }

  switchInspectorTab(tabName) {
    this.activeInspectorTab = tabName;
    document.querySelectorAll('.insp-tab').forEach((btn) => {
      btn.classList.toggle('active', btn.getAttribute('data-tab') === tabName);
    });
    this._renderRightInspector();
  }

  adjustFontSize(delta) {
    this.termFontSize = Math.max(10, Math.min(18, this.termFontSize + delta));
    document.getElementById('termFontSizeLabel').textContent = `${this.termFontSize}px`;
    this._renderRightInspector();
  }

  switchFloor(floorNum) {
    if (!this.state) return;
    this.state.active_floor = floorNum;
    this._renderAll();
  }

  async moveSelectedAgentToFloor(floorNum) {
    const num = parseInt(floorNum, 10) || 1;
    await fetch(`/api/agents/${encodeURIComponent(this.selectedAgentId)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ floor: num }),
    });
    this.state.active_floor = num;
    await this.refreshState();
  }

  async addFloor() {
    await fetch('/api/floors', { method: 'POST' });
    await this.refreshState();
  }

  toggleAddItemMenu() {
    document.getElementById('addItemDropdown').classList.toggle('open');
  }

  setBuildTool(tool) {
    this.activeBuildTool = tool || null;
    if (this.officeCanvas) {
      this.officeCanvas.buildTool = this.activeBuildTool;
    }
    const delBtn = document.getElementById('deleteModeBtn');
    if (delBtn) {
      const isDel = this.activeBuildTool && this.activeBuildTool.kind === 'delete';
      delBtn.style.borderColor = isDel ? '#f43f5e' : '';
      delBtn.style.color = isDel ? '#fda4af' : '';
      delBtn.textContent = isDel ? '🗑️ Deleting (Click Item)' : '🗑️ Delete';
    }
    const rotBtn = document.getElementById('rotateModeBtn');
    if (rotBtn) {
      const isRot = this.activeBuildTool && this.activeBuildTool.kind === 'rotate';
      rotBtn.style.borderColor = isRot ? '#a3e635' : '';
      rotBtn.style.color = isRot ? '#a3e635' : '';
      rotBtn.textContent = isRot ? '🔄 Rotating (Click Item)' : '🔄 Rotate (R)';
    }
    const hintEl = document.getElementById('canvasStatusHint');
    if (hintEl) {
      if (!this.activeBuildTool) {
        hintEl.textContent =
          '🖐️ Drag Mode • drag any item/wall to move • press R to rotate • right-click item/wall to delete';
        hintEl.style.color = '#d4d4d8';
      } else if (this.activeBuildTool.kind === 'delete') {
        hintEl.textContent =
          '🗑️ DELETE MODE ACTIVE • Click any wall, desk, door, chair, or plant to delete it (Right-click to exit)';
        hintEl.style.color = '#fda4af';
      } else if (this.activeBuildTool.kind === 'rotate') {
        hintEl.textContent =
          '🔄 ROTATE MODE ACTIVE • Click any wall, desk, chair, door, or table to rotate 90° (Right-click to exit)';
        hintEl.style.color = '#a3e635';
      } else if (this.activeBuildTool.kind === 'tile') {
        hintEl.textContent = `🎨 PAINTING FLOOR TILE: ${this.activeBuildTool.label} • Click or drag across the floor to paint (Right-click to exit)`;
        hintEl.style.color = '#a3e635';
      } else {
        hintEl.textContent = `🛠️ PLACING: ${this.activeBuildTool.label} (Press R to rotate) • Click any floor tile to place (Right-click to exit)`;
        hintEl.style.color = '#fde047';
      }
    }
  }

  async placeFurniture(kind, label, color) {
    document.getElementById('addItemDropdown').classList.remove('open');
    const floor = (this.state && this.state.active_floor) || 1;
    const gx = Math.floor(4 + Math.random() * 10);
    const gy = Math.floor(3 + Math.random() * 8);
    await this.placeFurnitureAt(kind, label, color, gx, gy, 0);
  }

  async placeFurnitureAt(kind, label, color, gx, gy, rotation = 0) {
    const floor = (this.state && this.state.active_floor) || 1;
    await fetch('/api/furniture', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ kind, label, floor, grid_x: gx, grid_y: gy, color, rotation }),
    });
    await this.refreshState();
  }

  async moveFurnitureItem(itemId, gx, gy) {
    await fetch(`/api/furniture/${encodeURIComponent(itemId)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ grid_x: gx, grid_y: gy }),
    });
    await this.refreshState();
  }

  async rotateFurnitureItem(itemId) {
    await fetch(`/api/furniture/${encodeURIComponent(itemId)}/rotate`, {
      method: 'POST',
    });
    await this.refreshState();
  }

  async deleteFurnitureItem(itemId) {
    await fetch(`/api/furniture/${encodeURIComponent(itemId)}`, {
      method: 'DELETE',
    });
    await this.refreshState();
  }

  async paintFloorTileAt(gx, gy, tileStyle) {
    const floor = (this.state && this.state.active_floor) || 1;
    const key = `${floor}:${gx},${gy}`;
    if (this.state && this.state.floor_tiles) {
      if (tileStyle === 'wood' || tileStyle === 'default') {
        delete this.state.floor_tiles[key];
      } else {
        this.state.floor_tiles[key] = tileStyle;
      }
      if (this.officeCanvas) {
        this.officeCanvas.floorTiles = this.state.floor_tiles;
      }
    }
    await fetch('/api/floor-tiles', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ floor, grid_x: gx, grid_y: gy, tile_style: tileStyle }),
    });
  }

  openAddAgentModal() {
    document.getElementById('addAgentModal').classList.add('open');
  }

  async openGitHubModal() {
    document.getElementById('githubOrgModal').classList.add('open');
    const listEl = document.getElementById('ghExistingReposList');
    listEl.textContent = 'Fetching repositories from https://github.com/JoeSecondBrainVault ...';
    try {
      const resp = await fetch('/api/github/repos');
      const data = await resp.json();
      const repos = data.repos || [];
      listEl.innerHTML = repos.length
        ? repos
            .map(
              (r) =>
                `<div style="margin-bottom:4px;">• <a href="${r.url}" target="_blank" style="color:#67e8f9;">${data.org}/${r.name}</a> <span style="color:#9ca3af;">[${r.visibility}]</span></div>`
            )
            .join('')
        : 'No repos found.';
    } catch (_) {
      listEl.textContent = 'Error loading org repos.';
    }
  }

  async submitGitHubRepo() {
    const repo_name = document.getElementById('ghRepoName').value.trim();
    const description = document.getElementById('ghRepoDesc').value.trim() || 'Created by HarnessAgents squad';
    const visibility = document.getElementById('ghRepoVis').value;
    if (!repo_name) return;

    const btn = document.getElementById('ghCreateBtn');
    btn.textContent = '⏳ Creating & Pushing to JoeSecondBrainVault...';
    btn.disabled = true;
    try {
      await fetch('/api/github/repos', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          repo_name,
          description,
          agent_id: this.selectedAgentId,
          visibility,
          push_to_github: true,
        }),
      });
      this.closeModals();
      await this.refreshState();
      await this.selectAgent(this.selectedAgentId);
    } finally {
      btn.textContent = '🚀 Scaffold & Push to JoeSecondBrainVault →';
      btn.disabled = false;
    }
  }

  openNewTaskModal() {
    const sel = document.getElementById('newTaskAgent');
    sel.innerHTML = (this.state.agents || [])
      .map((a) => `<option value="${a.id}">${a.display_title}</option>`)
      .join('');
    document.getElementById('newTaskModal').classList.add('open');
  }

  closeModals() {
    document.querySelectorAll('.modal-backdrop').forEach((m) => m.classList.remove('open'));
  }

  async submitNewAgent() {
    const name = document.getElementById('newAgentName').value.trim() || 'carlo';
    const role = document.getElementById('newAgentRole').value.trim() || 'DevOps & Cloud Specialist';
    const department = document.getElementById('newAgentDept').value.trim() || 'HarnessAgents';
    const model_id = document.getElementById('newAgentModel').value;
    const floor = (this.state && this.state.active_floor) || 1;

    const resp = await fetch('/api/agents', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, role, department, model_id, floor }),
    });
    const data = await resp.json();
    this.closeModals();
    await this.refreshState();
    if (data.agent && data.agent.id) {
      await this.selectAgent(data.agent.id);
    }
  }

  async submitNewTask() {
    const title = document.getElementById('newTaskTitle').value.trim();
    const description = document.getElementById('newTaskDesc').value.trim();
    const assigned_agent_id = document.getElementById('newTaskAgent').value;
    if (!title) return;
    await fetch('/api/kanban', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title, description, assigned_agent_id, priority: 'high' }),
    });
    this.closeModals();
    await this.refreshState();
  }

  async advanceTask(taskId, currentStatus) {
    const order = ['backlog', 'in_progress', 'review', 'done'];
    const idx = order.indexOf(currentStatus);
    const nextStatus = order[Math.min(order.length - 1, idx + 1)];
    await fetch(`/api/kanban/${taskId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: nextStatus }),
    });
    await this.refreshState();
  }

  async triggerAutoKanban() {
    await fetch('/api/kanban/auto-dispatch', { method: 'POST' });
    await this.refreshState();
    await this.selectAgent(this.selectedAgentId);
  }

  async openAgentIDE() {
    await fetch(`/api/agents/${encodeURIComponent(this.selectedAgentId)}/open-ide`, {
      method: 'POST',
    });
    await this.refreshState();
    await this.selectAgent(this.selectedAgentId);
  }

  async openAgentFolder() {
    await fetch(`/api/agents/${encodeURIComponent(this.selectedAgentId)}/open-folder`, {
      method: 'POST',
    });
    await this.refreshState();
    await this.selectAgent(this.selectedAgentId);
  }

  toggleAdvancedDrawer() {
    const drawer = document.getElementById('advancedToolsDrawer');
    const btn = document.getElementById('toggleToolsBtn');
    if (!drawer) return;
    const isHidden = drawer.style.display === 'none' || !drawer.style.display;
    drawer.style.display = isHidden ? 'block' : 'none';
    if (btn) {
      btn.style.borderColor = isHidden ? '#a3e635' : '';
      btn.style.color = isHidden ? '#a3e635' : '';
    }
  }

  insertQuickPrompt() {
    const samples = [
      'Build a Python calculator app with CLI and unit tests',
      'Build a modern HTML/CSS/JS scientific calculator web app',
      'Build a Python Todo CLI tracker with JSON storage',
      'Audit this workspace against OWASP ASVS 5.0.0 security rules',
    ];
    const box = document.getElementById('promptInputBox');
    box.value = samples[Math.floor(Math.random() * samples.length)];
    box.focus();
  }

  promptSpeechBubble() {
    const presets = ['SWELDO NA! 🎉', '0 Errors! 🚀', 'Tests Green! 🧪', 'Equipped 311 ECC! ⚡'];
    const pick = presets[Math.floor(Math.random() * presets.length)];
    fetch(`/api/agents/${encodeURIComponent(this.selectedAgentId)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ speech_bubble: pick }),
    }).then(() => this.refreshState());
  }

  startVoiceDictation() {
    const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRec) {
      const box = document.getElementById('promptInputBox');
      box.value = '[Voice Command] Run full TDD verification and security audit';
      return;
    }
    const rec = new SpeechRec();
    rec.lang = 'en-US';
    rec.onresult = (e) => {
      const transcript = e.results[0][0].transcript;
      document.getElementById('promptInputBox').value = transcript;
    };
    rec.start();
  }
}

window.addEventListener('DOMContentLoaded', () => {
  window.app = new HarnessOfficeApp();
  window.app.init();
});

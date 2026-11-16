/* Nexus Studio 3.0 — frontend sem frameworks e sem dados simulados. */
(() => {
  'use strict';

  const $ = (id) => document.getElementById(id);
  const state = {
    status: null,
    online: false,
    attachments: [],
    streaming: false,
    models: [],
    activeChat: ''
  };

  const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  })[c]);

  function showError(message) {
    const banner = $('errorBanner');
    banner.textContent = message;
    banner.hidden = false;
    clearTimeout(showError.timer);
    showError.timer = setTimeout(() => { banner.hidden = true; }, 7000);
  }

  async function api(path, options = {}) {
    const response = await fetch(path, {
      headers: options.body ? { 'Content-Type': 'application/json' } : {},
      ...options
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || data.ok === false) {
      throw new Error(data.error || `HTTP ${response.status}`);
    }
    return data;
  }

  const fmtGb = (value) => Number(value || 0).toFixed(1) + ' GB';

  async function refreshStatus() {
    try {
      state.status = await api('/api/status');
      const s = state.status;
      $('brandVersion').textContent = `${s.product} · v${s.version}`;
      $('installationId').textContent = 'instalação: ' + s.installation_id;
      $('miniPlatform').textContent = `${s.platform.system} / ${s.platform.arch}`;
      $('miniTier').textContent = s.hardware.tier;
      $('miniRam').textContent = fmtGb(s.hardware.ram_total_gb);
      $('miniEngine').textContent = s.engine.installed ? (s.engine.alive ? 'ativo' : 'instalado') : 'não instalado';
      $('metricCpu').textContent = `${s.hardware.cpu_cores} núcleos`;
      $('metricRam').textContent = fmtGb(s.hardware.ram_available_gb);
      $('metricVram').textContent = fmtGb(s.hardware.vram_total_gb);
      $('metricFs').textContent = s.hardware.filesystem;
      $('welcomeStatus').textContent = s.engine.alive
        ? `Motor ativo em 127.0.0.1:${s.engine.running.port}. Envie sua primeira mensagem.`
        : (s.startup_errors[0] || 'Motor indisponível. Use o painel Diagnóstico para verificar.');
      const pill = $('healthPill');
      pill.className = 'pill ' + (s.engine.alive ? 'ok' : 'warning');
      pill.textContent = s.engine.alive ? 'Motor online' : 'Motor indisponível';
      await refreshModels();
      renderRoute(s.route);
    } catch (err) {
      showError('Não foi possível consultar o status: ' + err.message);
    }
  }

  function renderRoute(route) {
    const panel = $('routePanel');
    if (!route) {
      panel.innerHTML = '<p class="muted">Envie uma mensagem para ver a decisão do roteador.</p>';
      return;
    }
    panel.innerHTML = `
      <div><strong>Modelo:</strong> ${escapeHtml(route.model_id)}</div>
      <div><strong>Agente:</strong> ${escapeHtml(route.agent_id)}</div>
      <div><strong>Contexto:</strong> ${route.context} tokens · <strong>Temperatura:</strong> ${route.temperature}</div>
      <div><strong>Fontes:</strong> ${escapeHtml(route.needs_web ? 'web + local' : 'locais')} · ${escapeHtml(route.needs_documents ? 'documentos' : 'sem documentos')}</div>
      <div><strong>Estimativa:</strong> ${route.estimated_seconds}s ${route.fallback_used ? '· fallback usado' : ''}</div>
      <ul>${(route.rationale || []).map((r) => `<li>${escapeHtml(r)}</li>`).join('')}</ul>`;
  }

  async function refreshModels() {
    try {
      const data = await api('/api/models');
      state.models = data.models;
      const select = $('modelSelect');
      const previous = select.value;
      select.innerHTML = data.models.map((m) =>
        `<option value="${escapeHtml(m.id)}" ${m.installed ? '' : 'disabled'}>${escapeHtml(m.name)}${m.installed ? '' : ' — não instalado'}</option>`
      ).join('');
      if (previous) select.value = previous;
      else if (state.status?.active_model) select.value = state.status.active_model;
      renderModelManager(data.models);
    } catch (err) {
      showError(err.message);
    }
  }

  function renderModelManager(models) {
    $('modelManager').innerHTML = models.map((m) => `
      <div class="model-card">
        <strong>${escapeHtml(m.name)}</strong>
        <div class="muted">${escapeHtml(m.category)} · ${m.size_gb.toFixed(2)} GB · RAM mín. ${m.min_ram_gb} GB · licença ${escapeHtml(m.license)}</div>
        <div class="muted">${escapeHtml(m.notes || '')}</div>
        <div class="hash">sha256: ${escapeHtml(m.files[0]?.sha256 || 'não informado')}</div>
        <div class="row">
          <span>${m.installed ? (m.verified ? '✅ instalado e verificado' : '⚠️ instalado, hash não verificado') : '⬇️ não instalado'}</span>
          ${m.installed
            ? `<button class="btn ghost" data-select="${escapeHtml(m.id)}">Ativar</button>`
            : `<button class="btn ghost" data-install="${escapeHtml(m.id)}">Instalar</button>`}
        </div>
      </div>`).join('');

    document.querySelectorAll('[data-select]').forEach((button) => {
      button.addEventListener('click', async () => {
        try {
          await api('/api/models/select', { method: 'POST', body: JSON.stringify({ id: button.dataset.select }) });
          await refreshStatus();
        } catch (err) { showError(err.message); }
      });
    });
    document.querySelectorAll('[data-install]').forEach((button) => {
      button.addEventListener('click', async () => {
        if (!$('chkDownloads').checked) {
          showError('Marque "Autorizar downloads verificados" antes de instalar.');
          return;
        }
        button.disabled = true;
        button.textContent = 'Baixando…';
        try {
          await api('/api/models/install', { method: 'POST', body: JSON.stringify({ id: button.dataset.install }) });
          await refreshStatus();
        } catch (err) { showError(err.message); }
        button.disabled = false;
        button.textContent = 'Instalar';
      });
    });
  }

  async function refreshHistory() {
    try {
      const term = $('historySearch').value.trim();
      const data = await api('/api/history');
      let chats = data.chats;
      if (term) {
        const search = await api('/api/history/search?q=' + encodeURIComponent(term));
        chats = search.chats || chats.filter((c) => c.title.toLowerCase().includes(term.toLowerCase()));
      }
      state.activeChat = data.active;
      $('historyList').innerHTML = chats.length
        ? chats.map((c) => `<button class="history-item ${c.id === data.active ? 'active' : ''}" data-sid="${escapeHtml(c.id)}">
            <span>${escapeHtml(c.title)}</span><small>${c.messages || 0}</small></button>`).join('')
        : '<p class="muted">Nenhuma conversa salva.</p>';
      document.querySelectorAll('[data-sid]').forEach((button) => {
        button.addEventListener('click', async () => {
          const chat = await api('/api/history/load?id=' + encodeURIComponent(button.dataset.sid));
          $('chatLog').innerHTML = '';
          (chat.messages || []).forEach((m) => appendMessage(m.role, m.content, m.source, null, false));
        });
      });
    } catch (err) {
      // Endpoint de busca pode não existir em versões antigas: usa filtro local.
      showError(err.message);
    }
  }

  function appendMessage(role, content, source, route, scroll = true) {
    const welcome = $('chatLog').querySelector('.welcome');
    if (welcome) welcome.remove();
    const wrap = document.createElement('div');
    wrap.className = `msg ${role === 'user' ? 'user' : 'assistant'}`;
    wrap.innerHTML = `
      <div class="avatar">${role === 'user' ? 'V' : 'N'}</div>
      <div class="msg-body">
        <div class="msg-meta"><span>${role === 'user' ? 'Você' : 'Nexus'}</span>${source ? `<span>${escapeHtml(source)}</span>` : ''}</div>
        <div class="msg-content"></div>
        <div class="citations"></div>
      </div>`;
    wrap.querySelector('.msg-content').textContent = content || '';
    $('chatLog').appendChild(wrap);
    if (route) renderRoute(route);
    if (scroll) $('chatLog').scrollTop = $('chatLog').scrollHeight;
    return wrap;
  }

  function renderCitations(node, citations) {
    if (!citations?.length) return;
    const box = node.querySelector('.citations');
    box.innerHTML = citations.map((c) =>
      `<span class="citation" title="${escapeHtml(c.doc_path)}">📄 ${escapeHtml(c.citation || c.doc_name)} · p.${c.page}</span>`
    ).join('');
  }

  async function sendMessage(text) {
    if (state.streaming || !text.trim()) return;
    state.streaming = true;
    $('btnSend').disabled = true;
    appendMessage('user', text, 'enviado');
    $('messageInput').value = '';
    $('charCount').textContent = '0 chars';
    const node = appendMessage('assistant', '', '');
    const contentNode = node.querySelector('.msg-content');
    const status = $('streamStatus');
    status.hidden = false;
    status.textContent = 'Consultando o motor local…';

    const payload = {
      message: text,
      attachments: state.attachments,
      agent: $('agentSelect').value,
      model: $('modelSelect').value,
      online: state.online
    };
    try {
      const response = await fetch('/api/chat_stream', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload)
      });
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        let index;
        while ((index = buffer.indexOf('\n\n')) !== -1) {
          const chunk = buffer.slice(0, index);
          buffer = buffer.slice(index + 2);
          const line = chunk.split('\n').find((l) => l.startsWith('data:'));
          if (!line) continue;
          let event;
          try { event = JSON.parse(line.slice(5).trim()); } catch (_) { continue; }
          if (event.type === 'status') status.textContent = event.text;
          else if (event.type === 'delta') contentNode.textContent += event.text;
          else if (event.type === 'error') {
            node.classList.add('error');
            contentNode.textContent = 'Erro: ' + event.error;
          } else if (event.type === 'done') {
            contentNode.textContent = event.reply;
            renderCitations(node, event.citations);
            renderRoute(event.route);
          }
          $('chatLog').scrollTop = $('chatLog').scrollHeight;
        }
      }
    } catch (err) {
      node.classList.add('error');
      contentNode.textContent = 'Falha de comunicação com o servidor local: ' + err.message;
    } finally {
      state.streaming = false;
      $('btnSend').disabled = false;
      status.hidden = true;
      state.attachments = [];
      $('attachmentBar').innerHTML = '';
      $('attachmentBar').hidden = true;
      refreshHistory();
    }
  }

  function readFileAsBase64(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result));
      reader.onerror = reject;
      reader.readAsDataURL(file);
    });
  }

  function kindOf(file) {
    if (file.type.startsWith('image/')) return 'image';
    const ext = file.name.split('.').pop().toLowerCase();
    if (['pdf', 'docx', 'xlsx', 'csv'].includes(ext)) return ext;
    return 'text';
  }

  async function attachFiles(fileList, target = 'chat') {
    for (const file of Array.from(fileList)) {
      try {
        const content = await readFileAsBase64(file);
        const data = await api('/api/upload', {
          method: 'POST', body: JSON.stringify({ name: file.name, kind: kindOf(file), content })
        });
        if (target === 'chat') {
          state.attachments.push({
            name: data.name, kind: data.kind, path: data.path,
            preview: data.preview || '', text: (data.text || '').slice(0, 4000)
          });
          const chip = document.createElement('span');
          chip.className = 'attachment-chip';
          chip.textContent = `📎 ${data.name}${data.chunks ? ' · ' + data.chunks + ' chunks' : ''}`;
          $('attachmentBar').appendChild(chip);
          $('attachmentBar').hidden = false;
        }
        await refreshDocs();
      } catch (err) {
        showError(`Falha ao anexar ${file.name}: ${err.message}`);
      }
    }
  }

  async function refreshDocs() {
    try {
      const data = await api('/api/docs');
      $('docList').innerHTML = data.documents.length
        ? data.documents.map((d) => `<div class="doc-card"><strong>${escapeHtml(d.name)}</strong>
            <div class="muted">${escapeHtml(d.kind)} · ${d.chars} chars · ${d.chunks} chunks · pág. ${d.page_count}</div>
            ${(d.warnings || []).map((w) => `<p>${escapeHtml(w)}</p>`).join('')}</div>`).join('')
        : '<p class="muted">Nenhum documento indexado.</p>';
    } catch (err) { showError(err.message); }
  }

  async function searchDocs(query) {
    if (!query.trim()) { $('docResults').innerHTML = ''; return; }
    try {
      const data = await api('/api/docs/search?q=' + encodeURIComponent(query));
      $('docResults').innerHTML = data.results.map((r) => `<div class="doc-card">
        <strong>${escapeHtml(r.citation)}</strong><div class="muted">${escapeHtml(r.source)} · score ${r.score}</div>
        <p>${escapeHtml(r.text)}</p></div>`).join('') || '<p class="muted">Nenhum trecho encontrado.</p>';
    } catch (err) { showError(err.message); }
  }

  async function runDoctor() {
    $('doctorPanel').innerHTML = '<p class="muted">Executando…</p>';
    try {
      const report = await api('/api/doctor');
      $('doctorPanel').innerHTML = report.checks.map((c) => `
        <div class="check-card ${c.ok ? 'good' : 'bad'}"><strong>${c.ok ? '✓' : '✗'} ${escapeHtml(c.name)}</strong>
        <div class="muted">${escapeHtml(c.detail)}</div></div>`).join('') +
        (report.warnings || []).map((w) => `<div class="check-card bad">${escapeHtml(w)}</div>`).join('');
    } catch (err) { showError(err.message); }
  }

  async function loadAgents() {
    const data = await api('/api/agents');
    $('agentSelect').innerHTML = data.agents.map((a) =>
      `<option value="${escapeHtml(a.id)}">${escapeHtml(a.label)} — ${escapeHtml(a.short)}</option>`).join('');
    $('agentList').innerHTML = data.agents.slice(1).map((a) =>
      `<span class="chip">${escapeHtml(a.label)}</span>`).join('');
  }

  function bindEvents() {
    $('chatForm').addEventListener('submit', (event) => {
      event.preventDefault();
      sendMessage($('messageInput').value);
    });
    $('messageInput').addEventListener('input', () => {
      $('charCount').textContent = $('messageInput').value.length + ' chars';
    });
    $('messageInput').addEventListener('keydown', (event) => {
      if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        sendMessage($('messageInput').value);
      }
    });
    $('fileInput').addEventListener('change', (event) => attachFiles(event.target.files, 'chat'));
    $('docInput').addEventListener('change', (event) => attachFiles(event.target.files, 'docs'));
    $('btnClear').addEventListener('click', async () => {
      await api('/api/clear', { method: 'POST', body: '{}' });
      $('chatLog').innerHTML = '<div class="welcome"><h1>Conversa limpa</h1><p>O histórico desta conversa foi apagado do drive.</p></div>';
    });
    $('btnNewChat').addEventListener('click', async () => {
      await api('/api/new_chat', { method: 'POST', body: '{}' });
      $('chatLog').innerHTML = '<div class="welcome"><h1>Nova conversa</h1><p>Pronto. Envie sua mensagem.</p></div>';
      refreshHistory();
    });
    $('btnRefreshHistory').addEventListener('click', refreshHistory);
    $('historySearch').addEventListener('input', () => {
      const term = $('historySearch').value.toLowerCase();
      document.querySelectorAll('[data-sid]').forEach((item) => {
        item.hidden = !item.textContent.toLowerCase().includes(term);
      });
    });
    $('btnOffline').addEventListener('click', () => setOnline(false));
    $('btnOnline').addEventListener('click', () => setOnline(true));
    $('btnTheme').addEventListener('click', () => {
      const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
      document.documentElement.dataset.theme = next;
      localStorage.setItem('nexus3-theme', next);
    });
    $('chkDownloads').addEventListener('change', async (event) => {
      await api('/api/models/authorize', {
        method: 'POST', body: JSON.stringify({ allow: event.target.checked })
      });
    });
    $('btnDoctor').addEventListener('click', runDoctor);
    $('docSearch').addEventListener('input', (event) => searchDocs(event.target.value));
    document.querySelectorAll('.tab').forEach((tab) => {
      tab.addEventListener('click', () => {
        document.querySelectorAll('.tab').forEach((t) => t.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach((t) => t.classList.remove('active'));
        tab.classList.add('active');
        $('tab-' + tab.dataset.tab).classList.add('active');
      });
    });
    document.addEventListener('dragover', (event) => event.preventDefault());
    document.addEventListener('drop', (event) => {
      event.preventDefault();
      if (event.dataTransfer?.files?.length) attachFiles(event.dataTransfer.files, 'chat');
    });
  }

  function setOnline(value) {
    state.online = value;
    $('btnOffline').classList.toggle('active', !value);
    $('btnOnline').classList.toggle('active', value);
    $('btnOffline').setAttribute('aria-pressed', String(!value));
    $('btnOnline').setAttribute('aria-pressed', String(value));
  }

  async function init() {
    document.documentElement.dataset.theme = localStorage.getItem('nexus3-theme') || 'dark';
    bindEvents();
    await Promise.all([refreshStatus(), refreshHistory(), refreshDocs(), loadAgents()]);
  }

  init().catch((err) => showError('Falha na inicialização: ' + err.message));
})();

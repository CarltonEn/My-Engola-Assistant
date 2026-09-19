(() => {
  const qs = (s) => document.querySelector(s);
  const auth = qs('#auth');
  const app = qs('#app');
  const authError = qs('#authError');
  const loginBtn = qs('#loginBtn');
  const setupBtn = qs('#setupBtn');
  const core = qs('#engolaCore');
  const settings = qs('#settings');
  const workspace = qs('#workspace');
  const messages = qs('#messages');
  const input = qs('#messageInput');
  const form = qs('#composer');
  const stateLabel = qs('#coreState');

  const b64ToBytes = (s) => { s=s.replace(/-/g,'+').replace(/_/g,'/'); while(s.length%4)s+='='; const bin=atob(s); return Uint8Array.from(bin,c=>c.charCodeAt(0)); };
  const bytesToB64 = (buf) => { let s=''; new Uint8Array(buf).forEach(b=>s+=String.fromCharCode(b)); return btoa(s).replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,''); };
  const creationOpts = (o) => ({...o,challenge:b64ToBytes(o.challenge),user:{...o.user,id:b64ToBytes(o.user.id)},excludeCredentials:(o.excludeCredentials||[]).map(x=>({...x,id:b64ToBytes(x.id)}))});
  const requestOpts = (o) => ({...o,challenge:b64ToBytes(o.challenge),allowCredentials:(o.allowCredentials||[]).map(x=>({...x,id:b64ToBytes(x.id)}))});
  const credentialJSON = (c) => ({id:c.id,rawId:bytesToB64(c.rawId),type:c.type,response:{clientDataJSON:bytesToB64(c.response.clientDataJSON),attestationObject:c.response.attestationObject?bytesToB64(c.response.attestationObject):undefined,authenticatorData:c.response.authenticatorData?bytesToB64(c.response.authenticatorData):undefined,signature:c.response.signature?bytesToB64(c.response.signature):undefined,userHandle:c.response.userHandle?bytesToB64(c.response.userHandle):null}});
  const api = async (url, opts={}) => { const r=await fetch(url,{credentials:'same-origin',...opts,headers:{'Content-Type':'application/json',...(opts.headers||{})}}); const d=await r.json().catch(()=>({})); if(!r.ok) throw new Error(d.error||d.detail||'Request failed'); return d; };
  const unlock = () => { auth.classList.add('hidden'); app.classList.remove('hidden'); loadSettingsStatus(); loadPanel('knowledge'); };
  const bootAuth = async () => { try { const s=await api('/api/auth/status'); if(s.authenticated){unlock();return;} if(s.setup_required){loginBtn.classList.add('hidden');setupBtn.classList.remove('hidden');document.querySelector('#authText').textContent='One-time setup. Register this device with your platform passkey.';} else { qs('#recoveryToggleBtn').classList.remove('hidden'); } } catch(e){authError.textContent=e.message;} };
  const setupOwner = async () => { try { authError.textContent=''; const o=await api('/api/auth/setup/options',{method:'POST'}); const c=await navigator.credentials.create({publicKey:creationOpts(o)}); await api('/api/auth/setup/verify',{method:'POST',body:JSON.stringify(credentialJSON(c))}); unlock(); } catch(e){authError.textContent=e.message;} };
  const loginOwner = async () => { try { authError.textContent=''; const o=await api('/api/auth/login/options',{method:'POST'}); const c=await navigator.credentials.get({publicKey:requestOpts(o)}); await api('/api/auth/login/verify',{method:'POST',body:JSON.stringify(credentialJSON(c))}); unlock(); } catch(e){authError.textContent=e.message;} };
  loginBtn?.addEventListener('click',loginOwner); setupBtn?.addEventListener('click',setupOwner);

  const setCoreState = (state) => {
    const next = state || 'idle';

    // Keep the existing CSS/UI state in sync.
    core.classList.remove('speaking','thinking','success','error');
    if (next !== 'idle') core.classList.add(next);

    stateLabel.textContent = ({
      idle:'Ready',
      thinking:'Working',
      speaking:'Speaking',
      success:'Done',
      error:'Needs attention'
    })[next] || 'Ready';

    // Drive the 3D core when it is available.
    if (window.Engola3D?.setState) {
      window.Engola3D.setState(next);
    }
  };
  window.EngolaVisual = {setState:setCoreState};

  const escape = (v) => v.replace(/[&<>\"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','\\':'&#92;','"':'&quot;'}[c]));
  const addMessage = (role, text) => {
    const el = document.createElement('div'); el.className = `message ${role}`;
    el.innerHTML = `<div class="meta">${role === 'user' ? 'YOU' : 'ENGOLA'}</div><div class="bubble">${escape(text).replace(/\n/g,'<br>')}</div><div class="reaction-row"><button class="reaction" data-reaction="👍">👍</button><button class="reaction" data-reaction="❤️">❤️</button><button class="reaction" data-reaction="✨">✨</button><button class="reaction" data-reaction="📌">📌</button></div>`;
    messages.appendChild(el); messages.scrollTop = messages.scrollHeight; return el;
  };

  form.addEventListener('submit', async (e) => {
    e.preventDefault(); const text = input.value.trim(); if (!text) return;
    addMessage('user', text); input.value=''; setCoreState('thinking');
    try {
      const r = await fetch('/api/chat', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:text})});
      const data = await r.json();
      if (!r.ok || !data.ok) throw new Error(data.error || 'Request failed');
      const m = addMessage('engola', data.answer || 'Done.');
      m.dataset.mode = data.mode || '';
      if (data.mode && data.mode !== 'provider') {
        const tag = document.createElement('div');
        tag.style.cssText = 'font-size:10px;color:var(--muted);margin-top:4px';
        tag.textContent = data.mode === 'local' ? '⚡ answered locally, no AI call' : `via ${data.mode}`;
        m.querySelector('.bubble').after(tag);
      }
      setCoreState('success'); setTimeout(()=>setCoreState('idle'), 900);
    } catch (err) {
      addMessage('engola', 'I ran into a problem completing that. I\u2019ll keep the failure visible without pretending it succeeded.');
      setCoreState('error'); setTimeout(()=>setCoreState('idle'), 1200);
    }
  });

  document.addEventListener('click', (e) => {
    const reaction = e.target.closest('[data-reaction]');
    if (reaction) { reaction.parentElement.querySelectorAll('.reaction').forEach(b=>b.style.opacity='.45'); reaction.style.opacity='1'; }
    const cmd = e.target.closest('[data-command]');
    if (cmd) { input.value = cmd.dataset.command; input.focus(); }
    if (e.target.closest('#settingsOpen') || e.target.closest('#settingsOpen2')) { settings.classList.add('open'); loadSettingsStatus(); }
    if (e.target.closest('#settingsClose')) settings.classList.remove('open');
    if (e.target.closest('#workspaceOpen') || e.target.closest('#workspaceOpen2')) workspace.classList.add('open');
    if (e.target.closest('#workspaceClose')) workspace.classList.remove('open');
    const bg = e.target.closest('[data-wallpaper]');
    if (bg) document.documentElement.style.setProperty('--wallpaper', bg.dataset.wallpaper === 'none' ? 'none' : `url("${bg.dataset.wallpaper}")`);
    const accent = e.target.closest('[data-accent]');
    if (accent) { document.documentElement.style.setProperty('--accent', accent.dataset.accent); localStorage.setItem('engola.accent', accent.dataset.accent); }
  });

  const savedAccent = localStorage.getItem('engola.accent'); if (savedAccent) document.documentElement.style.setProperty('--accent', savedAccent);
  setCoreState('idle');

  // =====================================================================
  // RECOVERY FLOW (lock screen) -- separate from normal login. Proves
  // identity via ENGOLA_RECOVERY_TOKEN, then permits registering ONE new
  // passkey. Never logs in by itself.
  // =====================================================================
  const recoveryToggleBtn = qs('#recoveryToggleBtn');
  const recoveryBox = qs('#recoveryBox');
  const recoveryStep2 = qs('#recoveryStep2');
  recoveryToggleBtn?.addEventListener('click', () => recoveryBox.classList.toggle('hidden'));
  qs('#recoveryStartBtn')?.addEventListener('click', async () => {
    try {
      authError.textContent = '';
      await api('/api/auth/recovery/start', {method:'POST', body: JSON.stringify({recovery_token: qs('#recoveryTokenInput').value.trim()})});
      recoveryStep2.classList.remove('hidden');
      authError.textContent = 'Recovery authorized. Register a new passkey within 10 minutes.';
      authError.style.color = 'var(--good)';
    } catch (e) { authError.style.color=''; authError.textContent = e.message; }
  });
  qs('#recoveryRegisterBtn')?.addEventListener('click', async () => {
    try {
      authError.textContent = '';
      const o = await api('/api/auth/recovery/register/options', {method:'POST'});
      const c = await navigator.credentials.create({publicKey: creationOpts(o)});
      await api('/api/auth/recovery/register/verify', {method:'POST', body: JSON.stringify(credentialJSON(c))});
      unlock();
    } catch (e) { authError.textContent = e.message; }
  });

  // =====================================================================
  // WORKSPACE TABS -- every panel below calls a real endpoint.
  // =====================================================================
  const escapeHtml = (v) => String(v ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
  const row = (title, subtitle, actionsHtml='') => `<div class="setting-row" style="flex-direction:column;align-items:stretch;gap:6px"><div style="display:flex;justify-content:space-between;gap:10px"><b>${title}</b><span style="color:var(--muted);font-size:12px">${subtitle}</span></div>${actionsHtml ? `<div style="display:flex;gap:6px;flex-wrap:wrap">${actionsHtml}</div>` : ''}</div>`;
  const smallBtn = (label, attrs='') => `<button class="icon-btn" style="width:auto;padding:0 10px;font-size:12px" ${attrs}>${label}</button>`;

  const panelLoaders = {};

  // ---------- Knowledge ----------
  async function loadKnowledge() {
    const list = qs('#knowledgeList');
    list.textContent = 'Loading…';
    try {
      const d = await api('/api/knowledge');
      list.innerHTML = d.sources.length ? d.sources.map(s => row(
        escapeHtml(s.title || s.url), `${s.kind} · ${s.characters} chars · ${s.status}`,
        smallBtn('Delete', `data-know-del="${s.id}"`)
      )).join('') : '<div style="color:var(--muted)">No sources yet.</div>';
    } catch (e) { list.textContent = e.message; }
  }
  panelLoaders.knowledge = loadKnowledge;
  qs('#knowledgeIngestBtn')?.addEventListener('click', async () => {
    const url = qs('#knowledgeUrl').value.trim();
    const status = qs('#knowledgeStatus');
    if (!url) { status.textContent = 'Enter a URL first.'; return; }
    status.textContent = 'Ingesting…';
    try { await api('/api/knowledge/ingest', {method:'POST', body: JSON.stringify({url})}); qs('#knowledgeUrl').value=''; status.textContent='Ingested.'; loadKnowledge(); }
    catch (e) { status.textContent = e.message; }
  });
  qs('#knowledgeUploadBtn')?.addEventListener('click', async () => {
    const fileInput = qs('#knowledgeFile');
    const status = qs('#knowledgeStatus');
    if (!fileInput.files.length) { status.textContent = 'Choose a file first.'; return; }
    status.textContent = 'Uploading…';
    try {
      const fd = new FormData(); fd.append('file', fileInput.files[0]);
      const r = await fetch('/api/knowledge/upload', {method:'POST', credentials:'same-origin', body: fd});
      const d = await r.json().catch(()=>({}));
      if (!r.ok) throw new Error(d.detail || d.error || 'Upload failed');
      status.textContent = 'Uploaded.'; fileInput.value=''; loadKnowledge();
    } catch (e) { status.textContent = e.message; }
  });
  qs('#knowledgeWikiBtn')?.addEventListener('click', async () => {
    const q = qs('#knowledgeWikiQuery').value.trim();
    const out = qs('#knowledgeWikiResults');
    if (!q) return;
    out.textContent = 'Searching…';
    try {
      const d = await api('/api/knowledge/wiki?query=' + encodeURIComponent(q));
      out.innerHTML = d.results.length ? d.results.map(r => row(`<a href="${r.url}" target="_blank" style="color:var(--text)">${escapeHtml(r.title)}</a>`, escapeHtml(r.description))).join('') : '<div style="color:var(--muted)">No results.</div>';
    } catch (e) { out.textContent = e.message; }
  });
  document.addEventListener('click', async (e) => {
    const del = e.target.closest('[data-know-del]');
    if (del) { try { await api('/api/knowledge/' + del.dataset.knowDel, {method:'DELETE'}); loadKnowledge(); } catch (err) { qs('#knowledgeStatus').textContent = err.message; } }
  });

  // ---------- Tasks ----------
  async function loadTasks() {
    const list = qs('#taskList');
    list.textContent = 'Loading…';
    try {
      const d = await api('/api/work/tasks');
      list.innerHTML = d.tasks.length ? d.tasks.map(t => row(
        `${t.status === 'done' ? '✅ ' : ''}${escapeHtml(t.title)}`, `#${t.id} · ${t.priority} · ${t.status}`,
        (t.status !== 'done' ? smallBtn('Complete', `data-task-done="${t.id}"`) : '') + smallBtn('Delete', `data-task-del="${t.id}"`)
      )).join('') : '<div style="color:var(--muted)">No tasks yet.</div>';
    } catch (e) { list.textContent = e.message; }
  }
  panelLoaders.tasks = loadTasks;
  qs('#taskAddBtn')?.addEventListener('click', async () => {
    const title = qs('#taskTitle').value.trim();
    const priority = qs('#taskPriority').value;
    const status = qs('#taskStatus');
    if (!title) { status.textContent = 'Title is required.'; return; }
    try { await api('/api/work/tasks', {method:'POST', body: JSON.stringify({title, priority})}); qs('#taskTitle').value=''; status.textContent=''; loadTasks(); }
    catch (e) { status.textContent = e.message; }
  });
  document.addEventListener('click', async (e) => {
    const done = e.target.closest('[data-task-done]');
    if (done) { try { await api('/api/work/tasks/' + done.dataset.taskDone, {method:'PATCH', body: JSON.stringify({status:'done'})}); loadTasks(); } catch (err) { qs('#taskStatus').textContent = err.message; } }
    const del = e.target.closest('[data-task-del]');
    if (del) { try { await api('/api/work/tasks/' + del.dataset.taskDel, {method:'DELETE'}); loadTasks(); } catch (err) { qs('#taskStatus').textContent = err.message; } }
  });

  // ---------- Memory ----------
  async function loadMemory() {
    const list = qs('#memoryList');
    list.textContent = 'Loading…';
    try {
      const d = await api('/api/memory');
      list.innerHTML = d.memories.length ? d.memories.map(m => row(escapeHtml(m.key), escapeHtml(m.value), smallBtn('Delete', `data-mem-del="${m.id}"`))).join('') : '<div style="color:var(--muted)">Nothing saved yet.</div>';
    } catch (e) { list.textContent = e.message; }
  }
  panelLoaders.memory = loadMemory;
  qs('#memoryAddBtn')?.addEventListener('click', async () => {
    const key = qs('#memoryKey').value.trim(); const value = qs('#memoryValue').value.trim();
    const status = qs('#memoryStatus');
    if (!key || !value) { status.textContent = 'Both key and value are required.'; return; }
    try { await api('/api/memory', {method:'POST', body: JSON.stringify({key, value})}); qs('#memoryKey').value=''; qs('#memoryValue').value=''; status.textContent=''; loadMemory(); }
    catch (e) { status.textContent = e.message; }
  });
  document.addEventListener('click', async (e) => {
    const del = e.target.closest('[data-mem-del]');
    if (del) { try { await api('/api/memory/' + del.dataset.memDel, {method:'DELETE'}); loadMemory(); } catch (err) { qs('#memoryStatus').textContent = err.message; } }
  });

  // ---------- Career ----------
  async function loadCareer() {
    const list = qs('#careerList');
    list.textContent = 'Loading…';
    try {
      const d = await api('/api/career/opportunities');
      list.innerHTML = d.opportunities.length ? d.opportunities.map(o => row(
        `${escapeHtml(o.title)}${o.company ? ' · ' + escapeHtml(o.company) : ''}`,
        `score ${o.score ?? 0}/100 · ${o.status}`,
        smallBtn('Rescore', `data-career-rescore="${o.id}"`) + smallBtn('Approve', `data-career-approve="${o.id}"`) + smallBtn('Submit', `data-career-submit="${o.id}"`)
      )).join('') : '<div style="color:var(--muted)">No opportunities yet.</div>';
    } catch (e) { list.textContent = e.message; }
  }
  panelLoaders.career = loadCareer;
  qs('#careerAddBtn')?.addEventListener('click', async () => {
    const title = qs('#careerTitle').value.trim();
    const company = qs('#careerCompany').value.trim();
    const url = qs('#careerUrl').value.trim();
    const description = qs('#careerDescription').value.trim();
    const status = qs('#careerStatus');
    if (!title || !description) { status.textContent = 'Title and description are required.'; return; }
    try {
      await api('/api/career/opportunities', {method:'POST', body: JSON.stringify({title, company, url, description})});
      qs('#careerTitle').value=''; qs('#careerCompany').value=''; qs('#careerUrl').value=''; qs('#careerDescription').value=''; status.textContent='';
      loadCareer();
    } catch (e) { status.textContent = e.message; }
  });
  document.addEventListener('click', async (e) => {
    const rescore = e.target.closest('[data-career-rescore]');
    if (rescore) { try { await api(`/api/career/opportunities/${rescore.dataset.careerRescore}/rescore`, {method:'POST'}); loadCareer(); } catch (err) { qs('#careerStatus').textContent = err.message; } }
    const approve = e.target.closest('[data-career-approve]');
    if (approve) { try { await api(`/api/career/opportunities/${approve.dataset.careerApprove}/approve`, {method:'POST', body: JSON.stringify({confirm:true})}); loadCareer(); } catch (err) { qs('#careerStatus').textContent = err.message; } }
    const submit = e.target.closest('[data-career-submit]');
    if (submit) { try { const d = await api(`/api/career/opportunities/${submit.dataset.careerSubmit}/submit`, {method:'POST'}); qs('#careerStatus').textContent = d.note || 'Marked ready.'; loadCareer(); } catch (err) { qs('#careerStatus').textContent = err.message; } }
  });

  // ---------- Uganda Knowledge ----------
  async function loadUganda() {
    const list = qs('#ugandaList');
    list.textContent = 'Loading…';
    try {
      const d = await api('/api/uganda/sources');
      list.innerHTML = d.sources.map(s => row(escapeHtml(s.name), `${escapeHtml(s.domain)} · ${escapeHtml(s.category)}`)).join('');
    } catch (e) { list.textContent = e.message; }
  }
  panelLoaders.uganda = loadUganda;

  // ---------- Permissions ----------
  async function loadPermissions() {
    const list = qs('#permissionsList');
    list.textContent = 'Loading…';
    try {
      const d = await api('/api/permissions');
      list.innerHTML = d.permissions.map(p => `<div class="setting-row"><span>${escapeHtml(p.name)}<br><small style="color:var(--muted)">${escapeHtml(p.scope)}</small></span><select data-perm-name="${escapeHtml(p.name)}" style="background:rgba(255,255,255,.05);color:var(--text);border:1px solid var(--line);border-radius:8px;padding:4px"><option value="allow" ${p.status==='allow'?'selected':''}>allow</option><option value="ask" ${p.status==='ask'?'selected':''}>ask</option><option value="deny" ${p.status==='deny'?'selected':''}>deny</option></select></div>`).join('');
    } catch (e) { list.textContent = e.message; }
  }
  panelLoaders.permissions = loadPermissions;
  document.addEventListener('change', async (e) => {
    const sel = e.target.closest('[data-perm-name]');
    if (sel) { try { await api('/api/permissions', {method:'POST', body: JSON.stringify({name: sel.dataset.permName, status: sel.value})}); } catch (err) { alert(err.message); loadPermissions(); } }
  });

  // ---------- Voice ----------
  qs('#voiceNarrateBtn')?.addEventListener('click', async () => {
    const text = qs('#voiceText').value.trim();
    const status = qs('#voiceStatus');
    const segs = qs('#voiceSegments');
    if (!text) { status.textContent = 'Enter text first.'; return; }
    status.textContent = 'Shaping…';
    try {
      const d = await api('/api/voice/narrate', {method:'POST', body: JSON.stringify({text})});
      status.textContent = d.note + ` (~${d.estimated_seconds}s)`;
      segs.innerHTML = d.segments.map(s => row(escapeHtml(s.text), `~${s.estimated_seconds}s · pause ${s.pause_after_ms}ms`)).join('');
    } catch (e) { status.textContent = e.message; }
  });
  qs('#voiceSpeakBtn')?.addEventListener('click', async () => {
    const text = qs('#voiceText').value.trim();
    const status = qs('#voiceStatus');
    const audioEl = qs('#voiceAudio');
    if (!text) { status.textContent = 'Enter text first.'; return; }
    status.textContent = 'Synthesizing…';
    try {
      const r = await fetch('/api/voice/speak', {method:'POST', credentials:'same-origin', headers:{'Content-Type':'application/json'}, body: JSON.stringify({text})});
      if (!r.ok) { const d = await r.json().catch(()=>({})); throw new Error(d.error || 'Speech synthesis failed'); }
      const blob = await r.blob();
      audioEl.src = URL.createObjectURL(blob);
      audioEl.style.display = 'block';
      audioEl.play();
      status.textContent = 'Playing.';
    } catch (e) { status.textContent = e.message; }
  });

  // ---------- Integrations (Google/GitHub) ----------
  async function loadIntegrations() {
    const box = qs('#integrationsStatus');
    box.textContent = 'Loading…';
    try {
      const d = await api('/api/integrations/status');
      box.innerHTML = row('Google', d.google.configured ? (d.google.connected ? 'connected' : 'configured, not connected') : 'not configured on server',
          d.google.configured ? (d.google.connected ? smallBtn('Disconnect', 'data-int-disconnect="google"') : smallBtn('Connect', 'data-int-connect="google"')) : '')
        + row('GitHub', d.github.configured ? (d.github.connected ? 'connected' : 'configured, not connected') : 'not configured on server',
          d.github.configured ? (d.github.connected ? smallBtn('Disconnect', 'data-int-disconnect="github"') : smallBtn('Connect', 'data-int-connect="github"')) : '');
      if (d.google.connected) box.innerHTML += row('Google Calendar (next 7 days)', '', smallBtn('Load', 'data-int-load="calendar"')) + '<div id="calendarResult"></div>';
      if (d.github.connected) box.innerHTML += row('GitHub repos', '', smallBtn('Load', 'data-int-load="repos"')) + '<div id="reposResult"></div>';
    } catch (e) { box.textContent = e.message; }
  }
  panelLoaders.integrations = loadIntegrations;
  document.addEventListener('click', (e) => {
    const connect = e.target.closest('[data-int-connect]');
    if (connect) window.location.href = `/api/${connect.dataset.intConnect}/authorize`;
    const disconnect = e.target.closest('[data-int-disconnect]');
    if (disconnect) { fetch(`/api/integrations/${disconnect.dataset.intDisconnect}/disconnect?confirm=1`, {credentials:'same-origin'}).then(loadIntegrations); }
    const load = e.target.closest('[data-int-load]');
    if (load) {
      if (load.dataset.intLoad === 'calendar') api('/api/integrations/google/calendar').then(d => { qs('#calendarResult').innerHTML = (d.events||[]).map(ev => row(escapeHtml(ev.summary||'(untitled)'), escapeHtml(ev.start?.dateTime || ev.start?.date || ''))).join(''); }).catch(err=>{qs('#calendarResult').textContent=err.message;});
      if (load.dataset.intLoad === 'repos') api('/api/integrations/github/repos').then(d => { qs('#reposResult').innerHTML = (d.repos||[]).map(r => row(escapeHtml(r.full_name||r.name), r.private ? 'private' : 'public')).join(''); }).catch(err=>{qs('#reposResult').textContent=err.message;});
    }
  });

  // ---------- Devices ----------
  async function loadDevices() {
    const list = qs('#deviceList');
    list.textContent = 'Loading…';
    try {
      const d = await api('/api/device');
      list.innerHTML = d.devices.length ? d.devices.map(dv => row(escapeHtml(dv.name), `${dv.platform} · ${dv.status}`)).join('') : '<div style="color:var(--muted)">No paired devices yet.</div>';
    } catch (e) { list.textContent = e.message; }
  }
  panelLoaders.devices = loadDevices;
  qs('#devicePairBtn')?.addEventListener('click', async () => {
    const status = qs('#deviceStatus');
    try { const d = await api('/api/device/pair', {method:'POST'}); status.textContent = `Pairing code: ${d.code} (expires in 10 min)`; }
    catch (e) { status.textContent = e.message; }
  });

  // ---------- Research ----------
  qs('#researchBtn')?.addEventListener('click', async () => {
    const q = qs('#researchQuery').value.trim();
    const status = qs('#researchStatus');
    const list = qs('#researchList');
    if (!q) return;
    status.textContent = 'Searching…'; list.innerHTML = '';
    try {
      const d = await api('/api/research/search?q=' + encodeURIComponent(q));
      status.textContent = '';
      list.innerHTML = d.results.length ? d.results.map(r => row(`<a href="${r.url}" target="_blank" style="color:var(--text)">${escapeHtml(r.title)}</a>`, escapeHtml(r.snippet))).join('') : 'No results.';
    } catch (e) { status.textContent = e.message; }
  });

  // ---------- System ----------
  async function loadSystem() {
    const box = qs('#systemStatus');
    box.textContent = 'Loading…';
    try {
      const d = await api('/api/system/status');
      box.innerHTML = [
        row('OpenAI', d.providers.openai ? 'configured' : 'not configured'),
        row('Gemini', d.providers.gemini ? 'configured' : 'not configured'),
        row('Voice (edge-tts)', d.voice.available ? `${d.voice.voice}` : 'not available'),
        row('Knowledge sources', String(d.knowledge_sources)),
        row('Paired devices', String(d.paired_devices)),
        row('Open tasks', String(d.open_tasks)),
        row('Active projects', String(d.active_projects)),
        row('Pending reminders', String(d.pending_reminders)),
        row('Telegram archive', d.telegram_archive_configured ? 'configured' : 'not configured'),
      ].join('');
    } catch (e) { box.textContent = e.message; }
  }
  panelLoaders.system = loadSystem;

  // ---------- Security ----------
  async function loadSecurity() {
    const box = qs('#securityStatus');
    box.textContent = 'Loading…';
    try {
      const d = await api('/api/auth/status');
      box.innerHTML = row('Owner', d.owner) + row('Authenticated this session', d.authenticated ? 'yes' : 'no') + row('WebAuthn available', d.webauthn_available ? 'yes' : 'no');
    } catch (e) { box.textContent = e.message; }
  }
  panelLoaders.security = loadSecurity;
  qs('#logoutBtn')?.addEventListener('click', async () => { try { await api('/api/auth/logout', {method:'POST'}); location.reload(); } catch (e) { alert(e.message); } });

  // ---------- Capabilities ----------
  async function loadCapabilities() {
    const list = qs('#capabilitiesList');
    list.textContent = 'Loading…';
    try {
      const d = await api('/api/capabilities');
      list.innerHTML = d.capabilities.map(c => row(c.name, `${c.state} · auth: ${c.auth} · risk: ${c.risk}`)).join('');
    } catch (e) { list.textContent = e.message; }
  }
  panelLoaders.capabilities = loadCapabilities;

  // ---------- Tab switching ----------
  function loadPanel(name) {
    document.querySelectorAll('.workspace-card').forEach(el => { el.style.display = el.dataset.panel === name ? 'block' : 'none'; });
    document.querySelectorAll('#workspaceTabs button').forEach(b => b.classList.toggle('active', b.dataset.panel === name));
    if (panelLoaders[name]) panelLoaders[name]();
  }
  qs('#workspaceTabs')?.addEventListener('click', (e) => {
    const btn = e.target.closest('button[data-panel]');
    if (btn) loadPanel(btn.dataset.panel);
  });

  // ---------- Settings connection status + side panel quick stats ----------
  async function loadSettingsStatus() {
    try {
      const d = await api('/api/system/status');
      qs('#connOpenAI').textContent = d.providers.openai ? 'Connected' : 'Not configured';
      qs('#connGemini').textContent = d.providers.gemini ? 'Connected' : 'Not configured';
      qs('#connTelegram').textContent = d.telegram_archive_configured ? 'Configured' : 'Not configured';
      qs('#sideOpenAI').textContent = d.providers.openai ? 'Connected' : 'Off';
      qs('#sideGemini').textContent = d.providers.gemini ? 'Connected' : 'Off';
    } catch (e) {}
    try {
      const d = await api('/api/integrations/status');
      qs('#connGoogle').textContent = d.google.connected ? 'Connected' : (d.google.configured ? 'Not connected' : 'Not configured');
      qs('#connGithub').textContent = d.github.connected ? 'Connected' : (d.github.configured ? 'Not connected' : 'Not configured');
      qs('#sideGoogleConn').textContent = d.google.connected ? 'Connected' : 'Off';
      qs('#sideGithubConn').textContent = d.github.connected ? 'Connected' : 'Off';
    } catch (e) {}
  }

  bootAuth();
})();

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
  const unlock = () => { auth.classList.add('hidden'); app.classList.remove('hidden'); };
  const bootAuth = async () => { try { const s=await api('/api/auth/status'); if(s.authenticated){unlock();return;} if(s.setup_required){loginBtn.classList.add('hidden');setupBtn.classList.remove('hidden');document.querySelector('#authText').textContent='One-time setup. Register this device with your platform passkey.';} } catch(e){authError.textContent=e.message;} };
  const setupOwner = async () => { try { authError.textContent=''; const o=await api('/api/auth/setup/options',{method:'POST'}); const c=await navigator.credentials.create({publicKey:creationOpts(o)}); await api('/api/auth/setup/verify',{method:'POST',body:JSON.stringify(credentialJSON(c))}); unlock(); } catch(e){authError.textContent=e.message;} };
  const loginOwner = async () => { try { authError.textContent=''; const o=await api('/api/auth/login/options',{method:'POST'}); const c=await navigator.credentials.get({publicKey:requestOpts(o)}); await api('/api/auth/login/verify',{method:'POST',body:JSON.stringify(credentialJSON(c))}); unlock(); } catch(e){authError.textContent=e.message;} };
  loginBtn?.addEventListener('click',loginOwner); setupBtn?.addEventListener('click',setupOwner);

  const setCoreState = (state) => {
    core.classList.remove('speaking','thinking','success','error');
    if (state) core.classList.add(state);
    stateLabel.textContent = ({idle:'Ready',thinking:'Working',speaking:'Speaking',success:'Done',error:'Needs attention'})[state] || 'Ready';
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
      setCoreState('success'); setTimeout(()=>setCoreState('idle'), 900);
    } catch (err) {
      addMessage('engola', 'I ran into a problem completing that. I’ll keep the failure visible without pretending it succeeded.');
      setCoreState('error'); setTimeout(()=>setCoreState('idle'), 1200);
    }
  });

  document.addEventListener('click', (e) => {
    const reaction = e.target.closest('[data-reaction]');
    if (reaction) { reaction.parentElement.querySelectorAll('.reaction').forEach(b=>b.style.opacity='.45'); reaction.style.opacity='1'; }
    const cmd = e.target.closest('[data-command]');
    if (cmd) { input.value = cmd.dataset.command; input.focus(); }
    if (e.target.closest('#settingsOpen')) settings.classList.add('open');
    if (e.target.closest('#settingsClose')) settings.classList.remove('open');
    if (e.target.closest('#workspaceOpen')) workspace.classList.add('open');
    if (e.target.closest('#workspaceClose')) workspace.classList.remove('open');
    const bg = e.target.closest('[data-wallpaper]');
    if (bg) document.documentElement.style.setProperty('--wallpaper', bg.dataset.wallpaper === 'none' ? 'none' : `url("${bg.dataset.wallpaper}")`);
    const accent = e.target.closest('[data-accent]');
    if (accent) { document.documentElement.style.setProperty('--accent', accent.dataset.accent); localStorage.setItem('engola.accent', accent.dataset.accent); }
  });

  const savedAccent = localStorage.getItem('engola.accent'); if (savedAccent) document.documentElement.style.setProperty('--accent', savedAccent);
  setCoreState('idle');
  bootAuth();
})();

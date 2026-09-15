(() => {
  const state = { audio:null };
  const qs = (s, r=document) => r.querySelector(s);
  const safe = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));

  function addCore(){
    if(qs('#engola-live-core')) return;
    const el=document.createElement('div'); el.id='engola-live-core';
    el.innerHTML='<div class="e17-ring"></div><div class="e17-orb"></div>';
    document.body.appendChild(el);
  }

  async function speak(text){
    if(!text) return;
    try{
      const r=await fetch('/api/voice/speak',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text})});
      if(!r.ok) throw new Error('voice unavailable');
      const blob=await r.blob();
      if(state.audio){state.audio.pause();URL.revokeObjectURL(state.audio.src)}
      const url=URL.createObjectURL(blob); const audio=new Audio(url); state.audio=audio;
      audio.onended=()=>URL.revokeObjectURL(url); await audio.play();
    }catch(e){
      // Browser speech is a silent fallback; prefer an en-GB voice when available.
      try{speechSynthesis.cancel(); const u=new SpeechSynthesisUtterance(text);u.lang='en-GB';u.rate=.94;u.pitch=.92;speechSynthesis.speak(u)}catch(_){ }
    }
  }

  function addBanner(){
    const chat=qs('#chat');
    if(!chat || qs('.e17-live-banner')) return;
    const b=document.createElement('div'); b.className='e17-live-banner';
    b.innerHTML='<span class="e17-live-dot"></span><span>Engola is listening</span><span style="margin-left:auto;opacity:.65">British neural voice</span>';
    chat.parentElement?.insertBefore(b, chat);
  }

  function observeMessages(){
    const chat=qs('#chat'); if(!chat) return;
    const add=()=>chat.querySelectorAll('.msg.assistant .bubble').forEach(b=>{
      if(b.dataset.e17Voice) return;
      b.dataset.e17Voice='1';
      const text=b.textContent.trim(); if(!text) return;
      const btn=document.createElement('button');btn.className='e17-voice-btn';btn.textContent='▶ Listen';
      btn.onclick=()=>speak(text); b.appendChild(btn);
    });
    add(); new MutationObserver(add).observe(chat,{childList:true,subtree:true});
  }

  window.EngolaSpeak = speak;
  window.addEventListener('load',()=>{addCore();addBanner();observeMessages();});
})();

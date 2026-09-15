(() => {
  const q=(s,r=document)=>r.querySelector(s);
  async function refresh(){
    try{
      const r=await fetch('/api/system/status'); if(!r.ok)return;
      const x=await r.json();
      let box=q('#engola-v18-status');
      if(!box){box=document.createElement('div');box.id='engola-v18-status';box.className='e18-grid';
        const host=q('#home .hero'); if(host&&host.parentElement)host.parentElement.insertBefore(box,host.nextElementSibling); else return;}
      box.innerHTML=`<div class="e18-tile"><b>Brain</b><small>${x.providers.gemini?'Gemini ready':x.providers.openai?'OpenAI ready':'Local engine'}</small></div><div class="e18-tile"><b>Voice</b><small>${x.voice.available?'British neural · '+x.voice.voice:'Voice offline'}</small></div><div class="e18-tile"><b>Knowledge</b><small>${x.knowledge_sources} sources in the vault</small></div><div class="e18-tile"><b>Devices</b><small>${x.paired_devices} paired · ${x.queued_commands} queued jobs</small></div>`;
    }catch(_){ }
  }
  window.addEventListener('load',()=>{refresh();setInterval(refresh,15000)});
})();

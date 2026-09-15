/* Engola v0.14: coherent Research/Knowledge workspace. */
(function(){
  'use strict';
  const $=id=>document.getElementById(id);
  const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const api=async(url,opts={})=>{const r=await fetch(url,{...opts,headers:{'Content-Type':'application/json',...(opts.headers||{})}});let d={};try{d=await r.json()}catch{}if(!r.ok)throw Error(d.error||d.detail||'Request failed');return d};
  function setPage(){
    let p=$('research');
    if(!p){p=document.createElement('section');p.id='research';p.className='page';document.querySelector('.content')?.appendChild(p)}
    p.innerHTML=`<div class="pageTitle"><h2>Research Vault</h2><p>Acquire, verify, store and retrieve knowledge without requiring a paid AI API.</p></div>
      <div class="v14ResearchGrid">
        <div class="v14Panel glass">
          <h3>Acquire a source</h3><p class="v14muted">Public webpage, PDF, or YouTube URL. Engola extracts what it can and stores the source privately.</p>
          <div class="v14Form"><input id="v14url" class="v14Input" placeholder="https://example.org/document.pdf">
            <div class="v14Row"><input id="v14category" class="v14Input" style="flex:1" placeholder="Category e.g. tax, accounting, AI"><select id="v14authority" class="v14Input" style="flex:1"><option value="official">Official / primary</option><option value="guidance">Official guidance</option><option value="international">International authority</option><option value="academic">Academic / reputable secondary</option><option value="wikipedia">Wikipedia / reference</option><option value="general">General web</option></select></div>
            <div class="v14Row"><button class="btn primary" id="v14Ingest">Study & store</button><button class="btn" id="v14Media">Open media</button></div><div id="v14AcquireStatus" class="v14Status"></div><div id="v14Preview"></div>
          </div>
        </div>
        <div class="v14Panel glass"><h3>Ask the vault</h3><p class="v14muted">Search the sources Engola has actually stored. Results are evidence, not invented knowledge.</p>
          <div class="v14Row"><input id="v14q" class="v14Input" placeholder="e.g. input tax, WebAuthn, VAT Act"><button class="btn primary" id="v14Search">Search</button></div><div id="v14Results" class="list" style="margin-top:10px"></div>
        </div>
        <div class="v14Panel glass"><h3>Wikipedia / general reference</h3><p class="v14muted">Useful for orientation, but not treated as equal to primary law or official guidance.</p>
          <div class="v14Row"><input id="v14wikiQ" class="v14Input" placeholder="Search Wikipedia"><button class="btn" id="v14Wiki">Search</button></div><div id="v14WikiResults" class="v14Wiki"></div>
        </div>
        <div class="v14Panel glass"><h3>Stored sources</h3><p class="v14muted">Your private knowledge index.</p><div id="v14Sources" class="list"></div></div>
      </div>`;
    bind(); loadSources();
  }
  function activate(){
    document.querySelectorAll('.page').forEach(x=>x.classList.toggle('active',x.id==='research'));
    document.querySelectorAll('[data-page]').forEach(x=>x.classList.toggle('active',x.dataset.page==='research'));
    const c=$('crumb');if(c)c.textContent='RESEARCH';
    setPage();
  }
  function bind(){
    $('v14Ingest').onclick=ingest;
    $('v14Media').onclick=mediaPreview;
    $('v14Search').onclick=searchVault;
    $('v14Wiki').onclick=searchWiki;
    $('v14q').onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();searchVault()}};
    $('v14wikiQ').onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();searchWiki()}};
  }
  async function ingest(){
    const url=$('v14url').value.trim(), status=$('v14AcquireStatus');
    if(!url){status.textContent='Enter a public URL.';status.className='v14Status bad';return}
    status.textContent='Acquiring and extracting…';status.className='v14Status';
    try{const d=await api('/api/knowledge/ingest',{method:'POST',body:JSON.stringify({url})});
      const s=d.source||{};status.textContent=`Stored source #${s.id??'?'}. ${s.characters??0} characters indexed.`;status.className='v14Status good';loadSources();
      if($('v14category').value.trim()||$('v14authority').value){
        // Existing ingest is authoritative extraction; metadata enrichment is intentionally deferred to a dedicated metadata route.
      }
      $('v14Preview').innerHTML=`<div class="v14Result"><b>${esc(s.title||url)}</b><small>${esc(s.kind||'source')} · ${esc(s.url||url)}</small></div>`;
    }catch(e){status.textContent=e.message;status.className='v14Status bad'}
  }
  async function mediaPreview(){
    const url=$('v14url').value.trim();if(!url)return;
    const box=$('v14Preview');box.innerHTML='<div class="v14Status">Resolving media…</div>';
    try{const d=await api('/api/media/youtube',{method:'POST',body:JSON.stringify({url})});
      box.innerHTML=`<div class="v14Result"><b>${esc(d.title||'YouTube video')}</b><small>${esc(d.author||'')} · ${esc(d.watch_url||url)}</small><iframe class="v14Video" src="${esc(d.embed_url)}" title="YouTube preview" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" allowfullscreen></iframe></div>`;
    }catch(e){box.innerHTML=`<div class="v14Status bad">${esc(e.message)}</div>`}
  }
  async function searchVault(){
    const q=$('v14q').value.trim(), box=$('v14Results');if(!q)return;
    box.innerHTML='<div class="v14Status">Searching…</div>';
    try{const d=await api('/api/knowledge/search',{method:'POST',body:JSON.stringify({query:q})});const rows=d.results||[];
      box.innerHTML=rows.length?rows.map(r=>`<div class="v14Result"><b>${esc(r.title||r.url||'Source')}</b><small>${esc(r.kind||'')} · ${esc(r.url||'')}</small><div class="v14SourceText">${esc(r.excerpt||r.text||'No excerpt returned.')}</div></div>`).join(''):'<div class="empty">No stored source matched that query.</div>';
    }catch(e){box.innerHTML=`<div class="v14Status bad">${esc(e.message)}</div>`}
  }
  async function searchWiki(){
    const q=$('v14wikiQ').value.trim(), box=$('v14WikiResults');if(!q)return;
    box.innerHTML='<div class="v14Status">Searching…</div>';
    try{const d=await api('/api/knowledge/wiki?query='+encodeURIComponent(q));const rows=d.results||[];
      box.innerHTML=rows.length?rows.map(r=>`<div class="v14Result"><b><a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.title)}</a></b><small>${esc(r.description||'No description')}</small></div>`).join(''):'<div class="empty">No Wikipedia result found.</div>';
    }catch(e){box.innerHTML=`<div class="v14Status bad">${esc(e.message)}</div>`}
  }
  async function loadSources(){
    const box=$('v14Sources');if(!box)return;box.innerHTML='<div class="v14Status">Loading…</div>';
    try{const d=await api('/api/knowledge');const rows=d.sources||[];
      box.innerHTML=rows.length?rows.slice(0,20).map(r=>`<div class="v14Result"><b>${esc(r.title||r.url)}</b><small>${esc(r.kind||'')} · ${esc(r.status||'')} · ${esc(r.url||'')}</small></div>`).join(''):'<div class="empty">No sources stored yet.</div>';
    }catch(e){box.innerHTML=`<div class="v14Status bad">${esc(e.message)}</div>`}
  }
  function intercept(e){
    const b=e.target.closest?.('[data-page="research"]');if(!b)return;
    e.preventDefault();e.stopImmediatePropagation();activate();
  }
  document.addEventListener('click',intercept,true);
  window.engolaV14Research=activate;
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>{const b=document.querySelector('[data-page="research"]');if(b)b.removeAttribute('onclick')});
  else {const b=document.querySelector('[data-page="research"]');if(b)b.removeAttribute('onclick')}
})();

/* Engola v0.16: capability connections + British voice. */
(function(){
'use strict';
const $=id=>document.getElementById(id);
const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const api=async(url,opts={})=>{const r=await fetch(url,{...opts,headers:{'Content-Type':'application/json',...(opts.headers||{})}});let d={};try{d=await r.json()}catch{}if(!r.ok)throw Error(d.error||d.detail||'Request failed');return d};
let voicePrefs={voice:'on',voice_auto:'off',voice_locale:'en-GB',voice_rate:'0.95'};
let voices=[];
function speak(text){if(!('speechSynthesis' in window))return false; window.speechSynthesis.cancel(); const u=new SpeechSynthesisUtterance(text); u.lang='en-GB'; u.rate=parseFloat(voicePrefs.voice_rate||'0.95'); const en=voices.filter(v=>/^en-GB$/i.test(v.lang)); if(en[0])u.voice=en[0]; window.speechSynthesis.speak(u); return true}
function loadVoices(){voices=window.speechSynthesis?.getVoices?.()||[]}
if('speechSynthesis' in window){loadVoices();window.speechSynthesis.onvoiceschanged=loadVoices}
async function loadPrefs(){try{const d=await api('/api/preferences');voicePrefs={...voicePrefs,...(d.preferences||{})}}catch{}}
async function savePref(key,value){try{await api('/api/preferences',{method:'POST',body:JSON.stringify({[key]:value})});voicePrefs[key]=value}catch(e){alert(e.message)}}
function addSpeakButtons(){document.querySelectorAll('.msg.assistant .bubble').forEach(b=>{if(b.querySelector('.v16-voicebar'))return;const text=b.innerText.trim();if(!text)return;const bar=document.createElement('div');bar.className='v16-voicebar';bar.innerHTML='<button class="btn v16-speak">▶ Speak (British)</button>';bar.querySelector('button').onclick=()=>{if(voicePrefs.voice==='off')return alert('Voice is switched off in Settings.'); if(!speak(text))alert('This browser does not provide speech synthesis.');};b.appendChild(bar);if(voicePrefs.voice_auto==='on')speak(text)})}
function buildConnections(){
 let p=$('capabilities'); if(!p){p=document.createElement('section');p.id='capabilities';p.className='page';document.querySelector('.content')?.appendChild(p)}
 p.innerHTML=`<div class="pageTitle"><h2>Capabilities & Connections</h2><p>One truthful registry for what Engola can use, where it runs, and what still needs your authorisation.</p></div>
 <div class="v16-grid">
  <div class="v16-card glass"><h3>Google</h3><p>Email and calendar access through OAuth. No credentials are stored in the browser.</p><div class="v16-actions"><button class="btn primary" id="v16Google">Connect Google</button><button class="btn" id="v16GoogleOff">Disconnect</button></div><div id="v16GoogleStatus" class="v16-status"></div></div>
  <div class="v16-card glass"><h3>GitHub</h3><p>Repository, issue, pull-request and CI capabilities after OAuth authorisation.</p><div class="v16-actions"><button class="btn primary" id="v16Github">Connect GitHub</button><button class="btn" id="v16GithubOff">Disconnect</button></div><div id="v16GithubStatus" class="v16-status"></div></div>
  <div class="v16-card glass"><h3>Device Agents</h3><p>Termux is the first agent. A future PC/Desktop agent uses the same pairing protocol.</p><div class="v16-actions"><button class="btn primary" id="v16Pair">Pair a device</button></div><div id="v16PairStatus" class="v16-status"></div><div id="v16PairCode"></div></div>
  <div class="v16-card glass"><h3>British Voice</h3><p>Free device-native speech. Engola requests an English (United Kingdom) voice; the exact available voice depends on your device/browser.</p><div class="v16-actions"><button class="btn primary" id="v16VoiceTest">Test British voice</button><button class="btn" id="v16VoiceToggle">Voice: ON</button><button class="btn" id="v16AutoToggle">Auto-speak: OFF</button></div><div id="v16VoiceStatus" class="v16-status"></div></div>
 </div>`;
 bindConnections(); loadConnectionStatus();
}
async function loadConnectionStatus(){
 try{const d=await api('/api/integrations/status');const g=d.google||{};const h=d.github||{};const a=d.archive||[];
   $('v16GoogleStatus').textContent=g.connected?'Connected':(g.configured?'Ready to authorise':'Server OAuth not configured');$('v16GoogleStatus').className='v16-status '+(g.connected?'v16-good':'v16-warn');
   $('v16GithubStatus').textContent=h.connected?'Connected':(h.configured?'Ready to authorise':'Server OAuth not configured');$('v16GithubStatus').className='v16-status '+(h.connected?'v16-good':'v16-warn');
   const tg=a.find(x=>x.provider==='telegram'); const gm=a.find(x=>x.provider==='gmail');
   if($('v16GoogleStatus')) $('v16GoogleStatus').title=`Google: ${g.connected?'connected':'not connected'} · Gmail archive: ${gm?.configured?'configured':'not configured'}`;
   if($('v16GithubStatus')) $('v16GithubStatus').title=`GitHub: ${h.connected?'connected':'not connected'} · Telegram archive: ${tg?.configured?'configured':'not configured'}`;
 }catch(e){$('v16GoogleStatus').textContent=e.message;$('v16GithubStatus').textContent=e.message}
 $('v16VoiceToggle').textContent='Voice: '+(voicePrefs.voice==='on'?'ON':'OFF');$('v16AutoToggle').textContent='Auto-speak: '+(voicePrefs.voice_auto==='on'?'ON':'OFF');
}
function bindConnections(){
 $('v16Google').onclick=async()=>{try{const d=await api('/api/integrations/status');if(!d.google?.configured){$('v16GoogleStatus').textContent='Google OAuth is not configured. Add the Google client credentials to Engola first.';$('v16GoogleStatus').className='v16-status v16-warn';return}location.href='/api/integrations/google/authorize'}catch(e){$('v16GoogleStatus').textContent=e.message}};
 $('v16GoogleOff').onclick=async()=>{try{await api('/api/integrations/google/disconnect',{method:'POST'});loadConnectionStatus()}catch(e){alert(e.message)}};
 $('v16Github').onclick=async()=>{try{const d=await api('/api/integrations/status');if(!d.github?.configured){$('v16GithubStatus').textContent='GitHub OAuth is not configured. Add the GitHub client credentials to Engola first.';$('v16GithubStatus').className='v16-status v16-warn';return}location.href='/api/integrations/github/authorize'}catch(e){$('v16GithubStatus').textContent=e.message}};
 $('v16GithubOff').onclick=async()=>{try{await api('/api/integrations/github/disconnect',{method:'POST'});loadConnectionStatus()}catch(e){alert(e.message)}};
 $('v16Pair').onclick=async()=>{try{const d=await api('/api/device/pair',{method:'POST'});$('v16PairCode').innerHTML='<div class="v16-device-code">'+esc(d.code||'')+'</div><div class="v16-status">Enter this one-time code on the device agent. It expires shortly and is single-use.</div>'}catch(e){$('v16PairStatus').textContent=e.message}};
 $('v16VoiceTest').onclick=()=>{if(speak('Good to have you back, Sir. How may I assist you today?'))$('v16VoiceStatus').textContent='British English voice requested (en-GB).';else $('v16VoiceStatus').textContent='Speech synthesis is unavailable in this browser.'};
 $('v16VoiceToggle').onclick=async()=>{await savePref('voice',voicePrefs.voice==='on'?'off':'on');loadConnectionStatus()};
 $('v16AutoToggle').onclick=async()=>{await savePref('voice_auto',voicePrefs.voice_auto==='on'?'off':'on');loadConnectionStatus()};
}
function intercept(e){const b=e.target.closest?.('[data-page="capabilities"]');if(!b)return;e.preventDefault();e.stopImmediatePropagation();buildConnections();document.querySelectorAll('.page').forEach(x=>x.classList.toggle('active',x.id==='capabilities'));document.querySelectorAll('[data-page]').forEach(x=>x.classList.toggle('active',x.dataset.page==='capabilities'));if($('crumb'))$('crumb').textContent='CAPABILITIES'}
document.addEventListener('click',intercept,true);
document.addEventListener('click',()=>setTimeout(addSpeakButtons,50),true);
loadPrefs();
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>{setTimeout(addSpeakButtons,200)});else setTimeout(addSpeakButtons,200);
window.engolaV16={buildConnections,speak};
})();
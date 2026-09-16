const tg = window.Telegram?.WebApp;
tg?.ready();
const app = document.getElementById('app');
const apiBase = window.location.origin + '/api/v1';
const initData = tg?.initData || '';
const tgUser = tg?.initDataUnsafe?.user || null;

async function api(path, opts={}) {
  const res = await fetch(apiBase + path, {headers:{'Content-Type':'application/json','X-Telegram-Init-Data': initData, ...(opts.headers||{})}, ...opts});
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

function shell(title, body) {
  app.innerHTML = `<div class="space-y-5"><div><h1 class="text-3xl font-bold">${title}</h1><p class="text-slate-400">🪙 ТГ-Джинни</p></div>${body}</div>`;
}

async function home(){
 shell('🧞‍♂️ ТГ-Джинни', `<p class="text-slate-300">Я попробую угадать, кого или что ты загадал.</p>
 <div class="grid gap-3"><button class="rounded-2xl bg-white text-slate-950 p-4 font-semibold" onclick="startGame()">🎮 Начать игру</button>
 <button class="rounded-2xl bg-slate-800 p-4" onclick="loadTasks()">🎁 Задания</button><button class="rounded-2xl bg-slate-800 p-4" onclick="loadShop()">🛍 Магазин</button><button class="rounded-2xl bg-slate-800 p-4" onclick="loadChannels()">📺 Мои каналы</button></div>`);
}
async function startGame(){
 try { const d=await api('/game/start',{method:'POST'}); renderQuestion(d); } catch(e){ shell('Ошибка', `<pre class="whitespace-pre-wrap">${e.message}</pre>`); }
}
function renderQuestion(d){
 shell(`Вопрос ${d.question_number} / ${d.total_questions}`, `<div class="rounded-3xl bg-slate-900 p-5 text-xl">${d.question.text}</div><div class="grid gap-2">${[['Да',1],['Скорее да',.75],['Не знаю',.5],['Скорее нет',.25],['Нет',0]].map(([t,v])=>`<button class="rounded-xl bg-slate-800 p-4" onclick="answer('${d.session_id}',${d.question.id},${v})">${t}</button>`).join('')}</div>`); }
async function answer(session,qid,v){ const d=await api(`/game/${session}/answer`,{method:'POST',body:JSON.stringify({question_id:qid,answer:v})}); if(d.finished){ const r=await api(`/game/${session}/result`); shell('🧞 Результат', `<div class="rounded-3xl bg-slate-900 p-5"><div class="text-2xl font-bold">${r.entity?.title||'Не угадал'}</div><div class="text-slate-400">${r.entity?.username||''}</div><div class="mt-3">Уверенность: ${Math.round((r.confidence||0)*100)}%</div></div><button class="w-full rounded-xl bg-white text-slate-950 p-4 font-semibold" onclick="home()">🎮 Играть снова</button>`);} else renderQuestion({...d,session_id:session}); }
async function loadTasks(){ try{ const ts=await api('/tasks'); shell('🎁 Задания', ts.length?`<div class="grid gap-3">${ts.map(t=>`<div class="rounded-2xl bg-slate-900 p-4"><div class="font-semibold">${t.title}</div><div class="text-slate-400">+${t.reward_coins} 🪙</div>${t.channel_username ? `<button class=\"mt-3 mr-2 rounded-xl bg-slate-700 px-4 py-2\" onclick=\"openChannel('${t.channel_username}')\">Открыть канал</button>` : ''}<button class="mt-3 rounded-xl bg-white text-slate-950 px-4 py-2" onclick="verifyTask(${t.id})">Проверить</button></div>`).join('')}</div>`:'<p>Заданий пока нет.</p>'); }catch(e){shell('Ошибка',e.message)} }
async function verifyTask(id){ try{ const r=await api(`/tasks/${id}/verify`,{method:'POST'}); alert(r.verified?'✅ Подписка подтверждена!':'❌ Подписка не найдена.'); }catch(e){alert(e.message)} }
async function loadShop(){ const items=await api('/shop'); shell('🛍 Магазин', items.length?items.map(i=>`<div class="rounded-2xl bg-slate-900 p-4"><div class="font-semibold">${i.title}</div><div>${i.price_coins} 🪙</div><button class="mt-3 rounded-xl bg-white text-slate-950 px-4 py-2" onclick="buy(${i.id})">Купить</button></div>`).join(''):'<p>Магазин пока пуст.</p>'); }
async function buy(id){ try{await api(`/shop/${id}/buy`,{method:'POST'}); alert('✅ Куплено');}catch(e){alert(e.message)} }
async function loadChannels(){ try { const cs=await api('/entities/mine'); shell('📺 Мои каналы', `<div class=\"grid gap-3\">${cs.map(c=>`<div class=\"rounded-2xl bg-slate-900 p-4\"><div class=\"font-semibold\">${c.title}</div><div class=\"text-slate-400\">${c.username||''}</div><div>${c.is_promoted?'🚀 Продвигается':'Обычный канал'}</div></div>`).join('')||'<p>Каналов пока нет.</p>'}</div><button class="rounded-xl bg-white text-slate-950 p-4 w-full" onclick="propose()">➕ Добавить канал</button>`); } catch(e) { shell('Ошибка', e.message); } }
async function propose(){ const title=prompt('Название канала'); const username=prompt('Ссылка или @username'); if(!title||!username)return; try{await api('/entities/propose',{method:'POST',body:JSON.stringify({title,username})}); alert('✅ Заявка отправлена на модерацию.');}catch(e){alert(e.message)} }
window.startGame=startGame; window.answer=answer; window.loadTasks=loadTasks; window.verifyTask=verifyTask; window.loadShop=loadShop; window.buy=buy; window.loadChannels=loadChannels; function openChannel(username){ const url='https://t.me/'+String(username).replace('@',''); tg?.openTelegramLink?.(url); }
window.propose=propose; window.openChannel=openChannel; home();

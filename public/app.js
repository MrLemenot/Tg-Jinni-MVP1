const tg = window.Telegram?.WebApp;
tg?.ready();
tg?.expand?.();

const app = document.getElementById('app');
const initData = tg?.initData || '';
const apiBase = `${window.location.origin}/api/v1`;

const esc = (value) => String(value ?? '').replace(/[&<>'"]/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[ch]));

async function api(path, opts = {}) {
  const headers = { ...(opts.body ? {'Content-Type':'application/json'} : {}), ...(opts.headers || {}), 'X-Telegram-Init-Data': initData };
  const res = await fetch(apiBase + path, { ...opts, headers });
  const text = await res.text();
  let body;
  try { body = text ? JSON.parse(text) : {}; } catch { body = { detail: text }; }
  if (!res.ok) throw new Error(body.detail?.message || body.detail || body.error || 'Ошибка запроса');
  return body;
}

function shell(title, body) {
  app.innerHTML = `
    <div class="space-y-4">
      <div class="flex items-center justify-between">
        <div><div class="text-2xl font-bold">${esc(title)}</div><div class="text-slate-400 text-sm">🧞 TG-Jinni</div></div>
        <button class="rounded-xl bg-slate-800 px-3 py-2" onclick="home()">⌂</button>
      </div>
      ${body}
    </div>`;
}

async function home() {
  try {
    const [me, promo] = await Promise.all([api('/me'), api('/promotions/feed')]);
    shell('TG-Jinni', `
      <div class="grid grid-cols-2 gap-3">
        <div class="rounded-2xl bg-slate-900 p-4"><div class="text-slate-400 text-sm">Монеты</div><div class="text-2xl font-bold">${me.coins_available} 🪙</div></div>
        <div class="rounded-2xl bg-slate-900 p-4"><div class="text-slate-400 text-sm">Игр сыграно</div><div class="text-2xl font-bold">${me.games_played}</div></div>
      </div>
      ${promo.campaign ? `<div class="rounded-2xl border border-slate-700 bg-slate-900 p-4"><div class="text-sm text-slate-400">Рекомендация</div><div class="font-semibold mt-1">${esc(promo.campaign.title)}</div><button class="mt-3 w-full rounded-xl bg-white text-slate-950 p-3 font-semibold" onclick="openPromo('${esc(promo.campaign.id)}','${esc(promo.campaign.url)}')">Подписаться</button></div>` : ''}
      <div class="grid gap-2">
        <button class="rounded-2xl bg-white text-slate-950 p-4 font-semibold" onclick="startGame()">🎮 Начать игру</button>
        <button class="rounded-2xl bg-slate-800 p-4" onclick="loadTasks()">🎁 Задания</button>
        <button class="rounded-2xl bg-slate-800 p-4" onclick="loadShop()">🛍 Магазин</button>
        <button class="rounded-2xl bg-slate-800 p-4" onclick="loadChannels()">📺 Мои каналы</button>
        ${me.is_admin ? '<button class="rounded-2xl bg-slate-800 p-4" onclick="loadAdmin()">⚙️ Админка</button>' : ''}
      </div>`);
  } catch (e) { shell('Ошибка', `<div class="rounded-2xl bg-slate-900 p-4 whitespace-pre-wrap">${esc(e.message)}</div>`); }
}

async function openPromo(id, url) {
  try { await api(`/promotions/${id}/click`, { method:'POST' }); } catch {}
  if (tg?.openTelegramLink) tg.openTelegramLink(url); else tg?.openLink?.(url);
}

async function startGame() {
  try { const d = await api('/game/start', {method:'POST'}); renderQuestion(d); }
  catch(e) { shell('Игра недоступна', `<div class="rounded-2xl bg-slate-900 p-4">${esc(e.message)}</div>`); }
}

function renderQuestion(d) {
  shell(`Вопрос ${d.question_number} / ${d.total_questions}`, `
    <div class="rounded-3xl bg-slate-900 p-5 text-xl">${esc(d.question.text)}</div>
    <div class="grid gap-2">
      ${[['Да',1],['Скорее да',.75],['Не знаю',.5],['Скорее нет',.25],['Нет',0]].map(([t,v]) => `<button class="rounded-xl bg-slate-800 p-4" onclick="answer('${d.session_id}',${d.question.id},${v})">${t}</button>`).join('')}
    </div>`);
}

async function answer(session, qid, value) {
  try {
    const d = await api(`/game/${session}/answer`, {method:'POST', body:JSON.stringify({question_id:qid,answer:value})});
    if (d.finished) {
      const r = await api(`/game/${session}/result`);
      shell('Результат', `<div class="rounded-3xl bg-slate-900 p-5 space-y-2"><div class="text-2xl font-bold">${esc(r.entity?.title || 'Не угадал')}</div><div class="text-slate-400">${esc(r.entity?.username || '')}</div><div>Уверенность: ${Math.round((r.confidence||0)*100)}%</div></div><button class="w-full rounded-xl bg-white text-slate-950 p-4 font-semibold" onclick="home()">На главную</button>`);
    } else renderQuestion({...d, session_id:session});
  } catch(e) { shell('Ошибка', `<div class="rounded-2xl bg-slate-900 p-4">${esc(e.message)}</div>`); }
}

async function loadTasks() {
  try {
    const ts = await api('/tasks');
    shell('Задания', ts.length ? `<div class="grid gap-3">${ts.map(t => `<div class="rounded-2xl bg-slate-900 p-4"><div class="font-semibold">${esc(t.title)}</div><div class="text-slate-400 mt-1">+${t.reward_coins} 🪙 · ${t.hold_hours} ч. холда</div>${t.channel_username ? `<button class="mt-3 mr-2 rounded-xl bg-slate-700 px-4 py-2" onclick="openChannel('${esc(t.channel_username)}')">Открыть канал</button>`:''}${t.user_status==='rewarded'?'<div class="mt-3 text-emerald-400">✅ Уже награждено</div>':`<button class="mt-3 rounded-xl bg-white text-slate-950 px-4 py-2" onclick="verifyTask(${t.id})">Проверить</button>`}</div>`).join('')}</div>` : '<div class="text-slate-400">Активных заданий пока нет.</div>');
  } catch(e) { shell('Ошибка', `<div>${esc(e.message)}</div>`); }
}

async function verifyTask(id) {
  try { const r = await api(`/tasks/${id}/verify`, {method:'POST'}); alert(r.verified ? `✅ Подписка подтверждена. Награда уйдёт в доступный баланс после ${r.hold_hours || 48} ч.` : '❌ Подписка не подтверждена.'); await loadTasks(); }
  catch(e) { alert(e.message); }
}

function openChannel(username) { const url='https://t.me/'+String(username).replace('@',''); tg?.openTelegramLink?.(url); }

async function loadShop() {
  try {
    const items = await api('/shop');
    shell('Магазин', items.length ? `<div class="grid gap-3">${items.map(i => `<div class="rounded-2xl bg-slate-900 p-4"><div class="font-semibold">${esc(i.title)}</div><div class="text-slate-400 mt-1">${esc(i.description||'')}</div><div class="mt-2">${i.price_coins} 🪙</div><button class="mt-3 rounded-xl bg-white text-slate-950 px-4 py-2" onclick="buy(${i.id})">Купить</button></div>`).join('')}` : '<div class="text-slate-400">Магазин пока пуст.</div>');
  } catch(e) { shell('Ошибка', `<div>${esc(e.message)}</div>`); }
}

async function buy(id) { try { await api(`/shop/${id}/buy`, {method:'POST'}); alert('✅ Куплено'); await loadShop(); } catch(e) { alert(e.message); } }

async function loadChannels() {
  try {
    const cs = await api('/entities/mine');
    shell('Мои каналы', `${cs.map(c => `<div class="rounded-2xl bg-slate-900 p-4 mb-3"><div class="font-semibold">${esc(c.title)}</div><div class="text-slate-400">${esc(c.username||'')}</div><div class="mt-2">${c.ownership_verified?'✅ Владелец подтверждён':'⚠️ Нужна проверка'} · ${c.is_promoted?'🚀 Продвигается':'Без продвижения'}</div>${c.promotion_status && c.promotion_status!=='none' ? `<div class="mt-2 text-sm text-slate-400">Показы: ${c.impressions_used}/${c.impressions_total} · клики: ${c.clicks_total}</div>`:''}<div class="grid gap-2 mt-3">${!c.ownership_verified?`<button class="rounded-xl bg-slate-700 p-3" onclick="reverify(${c.id})">Проверить владение</button>`:''}<button class="rounded-xl bg-white text-slate-950 p-3 font-semibold" onclick="buyPromotion(${c.id})">💳 Продвижение за 180 ₽</button></div></div>`).join('') || '<div class="text-slate-400">Каналов пока нет.</div>'}<button class="w-full rounded-xl bg-white text-slate-950 p-4 font-semibold" onclick="propose()">➕ Добавить канал</button>`);
  } catch(e) { shell('Ошибка', `<div>${esc(e.message)}</div>`); }
}

async function propose() {
  const title = prompt('Название канала');
  const username = prompt('Публичная ссылка или @username');
  if (!title || !username) return;
  try { await api('/entities/propose',{method:'POST',body:JSON.stringify({title,username})}); alert('✅ Заявка отправлена на модерацию.'); await loadChannels(); }
  catch(e) { alert(e.message); }
}

async function reverify(id) { try { const r=await api(`/entities/${id}/reverify`,{method:'POST'}); alert(r.verified?'✅ Владение подтверждено':'❌ Больше нельзя подтвердить владение.'); await loadChannels(); } catch(e){alert(e.message);} }

async function buyPromotion(entityId) {
  try {
    const d = await api('/promotions',{method:'POST',body:JSON.stringify({entity_id:entityId})});
    if (d.invoice_url && tg?.openInvoice) {
      tg.openInvoice(d.invoice_url, async (status) => { if(status==='paid') { alert('✅ Оплата получена'); await new Promise(r => setTimeout(r, 1200)); await loadChannels(); } else if(status==='failed') alert('❌ Платёж не прошёл'); });
    } else if (d.invoice_url) {
      tg?.openLink?.(d.invoice_url);
    }
  } catch(e) { alert(e.message); }
}

async function loadAdmin() {
  try {
    const [stats, pending] = await Promise.all([api('/admin/stats'), api('/admin/pending')]);
    shell('Админка', `<div class="grid grid-cols-2 gap-3 mb-3">
      <div class="rounded-2xl bg-slate-900 p-4"><div class="text-slate-400 text-sm">Пользователи</div><div class="text-2xl font-bold">${stats.users}</div></div>
      <div class="rounded-2xl bg-slate-900 p-4"><div class="text-slate-400 text-sm">В ожидании</div><div class="text-2xl font-bold">${stats.pending_channels}</div></div>
    </div>
    <div class="space-y-3">${pending.map(p => `<div class="rounded-2xl bg-slate-900 p-4"><div class="font-semibold">${esc(p.title)}</div><div class="text-slate-400">${esc(p.username||'')} · ${p.author_telegram_id}</div><div class="text-sm mt-2">Владение: ${p.ownership_verified?'✅':'❌'}</div><div class="grid grid-cols-2 gap-2 mt-3"><button class="rounded-xl bg-white text-slate-950 p-3" onclick="approvePending(${p.id})">Одобрить</button><button class="rounded-xl bg-slate-700 p-3" onclick="rejectPending(${p.id})">Отклонить</button></div></div>`).join('') || '<div class="text-slate-400">Новых заявок нет.</div>'}</div>`);
  } catch(e) { shell('Админка', `<div>${esc(e.message)}</div>`); }
}

async function approvePending(id) { try { await api(`/admin/pending/${id}/approve`, {method:'POST', body:JSON.stringify({comment:null})}); alert('✅ Одобрено'); await loadAdmin(); } catch(e) { alert(e.message); } }
async function rejectPending(id) { const comment = prompt('Причина отклонения (необязательно)') || null; try { await api(`/admin/pending/${id}/reject`, {method:'POST', body:JSON.stringify({comment})}); alert('✅ Отклонено'); await loadAdmin(); } catch(e) { alert(e.message); } }

window.loadAdmin=loadAdmin; window.approvePending=approvePending; window.rejectPending=rejectPending;
window.home=home; window.startGame=startGame; window.answer=answer; window.loadTasks=loadTasks; window.verifyTask=verifyTask; window.loadShop=loadShop; window.buy=buy; window.loadChannels=loadChannels; window.propose=propose; window.openChannel=openChannel; window.reverify=reverify; window.buyPromotion=buyPromotion; window.openPromo=openPromo;

const screen = new URLSearchParams(location.search).get('screen');
if (screen === 'tasks') loadTasks(); else if (screen === 'channels') loadChannels(); else if (screen === 'admin') loadAdmin(); else home();

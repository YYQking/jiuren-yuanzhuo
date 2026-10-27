/* 方案 B 的脚本：叠牌 → 发牌摊开 → 按下去 → 开桌。 */

const $ = (s) => document.querySelector(s);

const DECKS = {
  event: [
    ['qian', '乾明', '乾 · 天'], ['kun', '坤兰', '坤 · 地'],
    ['zhen', '震山', '震 · 雷'], ['xun', '巽竹', '巽 · 风'],
    ['kan', '坎川', '坎 · 水'], ['li', '离霞', '离 · 火'],
    ['gen', '艮石', '艮 · 山'], ['dui', '兑溪', '兑 · 泽'],
  ],
  business: [
    ['trend', '趋势分析师', '看大势'], ['industry', '行业从业者', '知道内情'],
    ['builder', '创业实践者', '真做过'], ['technology', '技术与实现顾问', '能不能做'],
    ['need', '真实需求者', '到底要什么'], ['bystander', '普通路人', '常识'],
    ['researcher', '用户研究员', '要证据'], ['creative', '跨界创意者', '歪招'],
    ['skeptic', '怀疑者', '泼冷水'],
  ],
};

const state = { mode: 'event', dealt: false, down: new Set() };
let cards = [];

function buildDeck() {
  const deck = $('#deck');
  deck.innerHTML = '';
  cards = DECKS[state.mode].map(([id, name, tag], i) => {
    const card = document.createElement('div');
    card.className = 'card back';
    card.style.setProperty('--dx', '0px');
    card.style.setProperty('--dy', '0px');
    card.style.setProperty('--rot', '0deg');
    // 叠着的时候：每张错开一点、各转一点点，像手里攥着一副牌
    card.style.transform =
      `translate(${i * 2.6 - 9}px, ${i * -3.2 + 10}px) rotate(${(i - 3.5) * 1.1}deg)`;
    card.innerHTML = `
      <div class="face">
        <img src="../assets/avatars/${id}.svg" alt="">
        <span class="nm">${name}</span>
        <span class="gua">${tag}</span>
        <span class="mark">阳</span>
      </div>`;
    card.addEventListener('click', () => toggleDown(i));
    deck.appendChild(card);
    return card;
  });
  state.dealt = false;
  state.down.clear();
  $('#openBtn').disabled = true;
  $('#dealBtn').textContent = '发 牌';
  updateNote();
}

function layoutFan() {
  const w = $('#deck').clientWidth;
  const n = cards.length;
  const spread = Math.min(w * 0.70, 960);
  const arc = 0.34;
  cards.forEach((card, i) => {
    const t = n === 1 ? 0.5 : i / (n - 1);
    const x = (t - 0.5) * spread;
    const rot = (t - 0.5) * arc * 180 / Math.PI * 0.5;
    const lift = Math.cos((t - 0.5) * arc * 2) * 34 - 34;
    card.classList.remove('back');
    card.style.setProperty('--dx', `${x}px`);
    card.style.setProperty('--dy', `${lift}px`);
    card.style.setProperty('--rot', `${rot}deg`);
    card.style.transform = `translate(${x}px, ${lift}px) rotate(${rot}deg)`;
    card.style.zIndex = String(10 + i);
    card.style.transitionDelay = `${i * 55}ms`;
  });
}

function deal() {
  if (state.dealt) {
    // 再点一次 = 重新发牌
    state.down.clear();
    buildDeck();
    setTimeout(deal, 60);
    return;
  }
  state.dealt = true;
  $('#dealBtn').textContent = '重新发牌';
  layoutFan();
  setTimeout(() => {
    cards.forEach((c) => { c.style.transitionDelay = '0ms'; });
    $('#openBtn').disabled = false;
    updateNote();
  }, 620);
}

function toggleDown(i) {
  const card = cards[i];
  if (!state.dealt) {
    deal();
    return;
  }
  if (state.down.has(i)) {
    state.down.delete(i);
    card.classList.remove('down');
  } else {
    if (state.down.size >= cards.length - 2) {
      $('#hallHint').textContent = '至少留两个人，不然没人吵。';
      return;
    }
    state.down.add(i);
    card.classList.add('down');
  }
  updateNote();
}

function updateNote() {
  const on = cards.length - state.down.size;
  const note = $('#footNote');
  if (!note) return;
  note.textContent = state.dealt ? `桌上 ${on} 张 · 按下去 ${state.down.size} 张` : `牌堆 ${cards.length} 张`;
  $('#hallHint').textContent = state.dealt
    ? '按下去的牌不上桌。议题写在绒面上那张单子上。'
    : '先发牌，把不想让上桌的那张按下去。';
}

document.querySelectorAll('.tab').forEach((tab) => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach((t) => t.classList.toggle('is-on', t === tab));
    state.mode = tab.dataset.mode;
    buildDeck();
  });
});

$('#dealBtn').addEventListener('click', deal);
$('#openBtn').addEventListener('click', () => {
  if (!$('#slipInput').value.trim()) {
    $('#hallHint').textContent = '议题还空着，随便写一句。';
    $('#slipInput').focus();
    return;
  }
  window.location.href = 'index.html';
});

buildDeck();

/* 大厅原型：两张桌子、一个议题框、一排座位、一个开桌键。
   只做交互验证，不连后端——点「开桌」就进赌桌页。 */

const MODES = {
  business: {
    title: '商业痛点桌',
    note: '九个人，九个立场，最后落到一份机会档案',
    startSub: '商业痛点桌 · 9 人 · 约 21 条',
    hint: '说一件让你难受的具体事——谁在什么时候为难谁。别写"行业痛点"这种词。',
    topics: [
      '小区门口的修鞋摊关了，老人宁可坐两站公交去修鞋，也不愿意用手机下单',
      '我们给餐馆做点单小程序，老板装了三个月又换回纸菜单，说"太麻烦"',
      '公司花钱买了协作软件，开会还是靠微信群，通知永远有人没看见',
    ],
    seats: [
      ['trend', '趋势分析师', '大势'],
      ['industry', '行业从业者', '内情'],
      ['builder', '创业实践者', '落地'],
      ['technology', '技术与实现顾问', '可行'],
      ['need', '真实需求者', '要什么'],
      ['bystander', '普通路人', '常识'],
      ['researcher', '用户研究员', '证据'],
      ['creative', '跨界创意者', '歪招'],
      ['skeptic', '怀疑者·风险评审', '泼冷水'],
    ],
  },
  event: {
    title: '八卦桌',
    note: '八个人，各有各的脾气：先阳面，聊深了翻阴面',
    startSub: '八卦桌 · 8 人 · 约 20 条',
    hint: '写清谁跟谁、在哪儿、什么时候。有细节的瓜才有的聊。',
    topics: [
      '某小区物业把业主的固定车位转租给了外面的人，业主群吵了一整天',
      '一家奶茶店被拍到后厨有蟑螂，店主说是同行陷害，双方各执一词',
      '网红餐厅排队两小时，进门发现隔壁桌是同一个老板开的另一家',
    ],
    seats: [
      ['qian', '乾明', '乾 · 天'],
      ['kun', '坤兰', '坤 · 地'],
      ['zhen', '震山', '震 · 雷'],
      ['xun', '巽竹', '巽 · 风'],
      ['kan', '坎川', '坎 · 水'],
      ['li', '离霞', '离 · 火'],
      ['gen', '艮石', '艮 · 山'],
      ['dui', '兑溪', '兑 · 泽'],
    ],
  },
};

const state = { mode: 'event', topicIndex: 0 };

const $ = (sel) => document.querySelector(sel);

function drawRoomDots() {
  document.querySelectorAll('.room').forEach((room) => {
    const holder = room.querySelector('.room-seats');
    const n = Number(holder.dataset.seats);
    holder.innerHTML = '';
    for (let i = 0; i < n; i += 1) {
      const a = (-90 + (i + 0.5) * (360 / n)) * Math.PI / 180;
      const dot = document.createElement('i');
      dot.style.left = `${50 + 46 * Math.cos(a)}%`;
      dot.style.top = `${50 + 42 * Math.sin(a)}%`;
      holder.appendChild(dot);
    }
  });
}

function renderSeats() {
  const mode = MODES[state.mode];
  const strip = $('#seatStrip');
  strip.innerHTML = '';
  strip.style.gridTemplateColumns = `repeat(${mode.seats.length}, 1fr)`;
  mode.seats.forEach(([id, name, tag]) => {
    const chip = document.createElement('button');
    chip.className = 'seat-chip is-on';
    chip.type = 'button';
    chip.innerHTML = `
      <img src="../assets/avatars/${id}.svg" alt="">
      <span class="nm">${name}</span>
      <span class="tag">${tag}</span>`;
    chip.addEventListener('click', () => chip.classList.toggle('is-on'));
    strip.appendChild(chip);
  });
  $('#seatsNote').textContent = state.mode === 'event'
    ? '八个人，各带两面：阳面客气，阴面才说真话'
    : '九个人，各管一块：有人拍板，有人泼冷水';
}

function syncUi() {
  const mode = MODES[state.mode];
  document.querySelectorAll('.room').forEach((room) => {
    room.classList.toggle('is-on', room.dataset.mode === state.mode);
  });
  $('#composerHint').textContent = mode.hint;
  $('#startSub').textContent = mode.startSub;
  $('#topicInput').value = mode.topics[state.topicIndex % mode.topics.length];
  renderSeats();
}

document.querySelectorAll('.room').forEach((room) => {
  room.addEventListener('click', () => {
    state.mode = room.dataset.mode;
    state.topicIndex = 0;
    syncUi();
  });
});

$('#diceBtn').addEventListener('click', () => {
  state.topicIndex += 1;
  const mode = MODES[state.mode];
  $('#topicInput').value = mode.topics[state.topicIndex % mode.topics.length];
});

$('#hotspotBtn').addEventListener('click', () => {
  $('#composerHint').textContent = '（原型示意）这里会打开今天的新闻列表，点一条就把它填进议题框。';
});

$('#startBtn').addEventListener('click', () => {
  const topic = $('#topicInput').value.trim();
  if (!topic) {
    $('#composerHint').textContent = '先写一句要聊什么，再开桌。';
    $('#topicInput').focus();
    return;
  }
  window.location.href = 'index.html';
});

drawRoomDots();
syncUi();

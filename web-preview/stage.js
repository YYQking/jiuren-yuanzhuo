/* S1「赌桌」的交互：点一次走一条，绝不自动播放。
   原型只演示手感，数据是死的（data.js），不联网、不调模型。

   Qt 落地备忘：
   - 席位定位＝算好像素坐标后 setGeometry，窗口 resize 时重算（同这里的 layout()）
   - 逐句浮现＝QTimer 逐句 append 到只读 QTextEdit，或给每句做一个淡入的 QLabel
   - 光环／聚光＝QGraphicsDropShadowEffect（color + blurRadius）
   - 回应连线＝自绘 QWidget 的 paintEvent 画 QPainterPath（同这里的 SVG path）
   - 暗牌翻面＝QPropertyAnimation 分帧改 QTransform 的 m22（rotateY），或两张 QPixmap 轮换
*/

const DEMO = window.DEMO;

const el = {
  topic: document.getElementById('topic'),
  tableName: document.getElementById('tableName'),
  counter: document.getElementById('counter'),
  hint: document.getElementById('hint'),
  voiceover: document.getElementById('voiceover'),
  table: document.getElementById('table'),
  platePhase: document.getElementById('platePhase'),
  plateSeal: document.getElementById('plateSeal'),
  plateCount: document.getElementById('plateCount'),
  potChips: document.getElementById('potChips'),
  dealer: document.getElementById('dealer'),
  seats: document.getElementById('seats'),
  replies: document.getElementById('replies'),
  speech: document.getElementById('speech'),
  who: document.getElementById('who'),
  faceChip: document.getElementById('faceChip'),
  intentChip: document.getElementById('intentChip'),
  replyChip: document.getElementById('replyChip'),
  wave: document.getElementById('wave'),
  body: document.getElementById('body'),
};

const FACE_TEXT = { yang: '阳面', yin: '阴面' };
const INTENT_TEXT = {
  initial: '开场',
  elaborate: '展开',
  challenge: '质疑',
  support: '附和',
  question: '追问',
  synthesize: '收束',
};

/* 阶段名统一成两个字，而且要文雅——混着 2/3/4 个字，字距一拉开就显得土。
   这套词只改"显示"，不动数据。 */
const PHASE_TEXT = {
  '开场': '起局',
  '独立观点': '立论',
  '正反交锋': '交锋',
  '阶段总结': '收束',
  '回答提问': '应答',
  '补充观点': '补述',
  '正面反驳': '争锋',
};
const SEAL_NUM = ['壹', '贰', '叁', '肆', '伍', '陆', '柒', '捌', '玖'];
const CN_NUM = { 1: '一', 2: '二', 3: '三', 4: '四', 5: '五', 6: '六', 7: '七', 8: '八', 9: '九', 10: '十' };
const TRIGRAM_GLYPH = /[☰☱☲☳☴☵☶☷]/;

let index = -1;
let started = false;
let revealTimer = null;
let seatNodes = new Map();
let geo = { cx: 0, cy: 0, rx: 0, ry: 0 };
let phaseOrder = [];

/* ── 起手：铺桌子、摆席位、发暗牌 ───────────────────── */
function boot() {
  el.topic.textContent = DEMO.topic;
  el.tableName.textContent = DEMO.section_label;
  el.plateCount.textContent = `${CN_NUM[DEMO.seats.length] || DEMO.seats.length} 人围坐`;
  el.counter.textContent = `第 0 / ${DEMO.turns.length} 条`;

  for (const turn of DEMO.turns) {
    if (turn.phase && !phaseOrder.includes(turn.phase)) phaseOrder.push(turn.phase);
  }

  for (const seat of DEMO.seats) {
    const glyph = (String(seat.trigram).match(TRIGRAM_GLYPH) || ['☰'])[0];
    const node = document.createElement('div');
    node.className = 'seat';
    node.dataset.face = 'yang';
    node.innerHTML = `
      <div class="seat-face"><img src="../assets/avatars/${seat.id}.svg" alt=""></div>
      <div class="chips"><i></i><i></i><i></i></div>
      <span class="seat-name">${seat.name}</span>
      <span class="seat-duty">${seat.duty}</span>
      <div class="card" title="暗牌：这个人还没翻出来的那一面">
        <div class="card-inner">
          <div class="card-back">${glyph}</div>
          <div class="card-front">阴</div>
        </div>
      </div>`;
    node.title = `${seat.name}（${seat.trigram}）\n阳面：${seat.yang}\n阴面：${seat.yin}\n\n${seat.duty}`;
    el.seats.appendChild(node);
    seatNodes.set(seat.id, node);
  }

  layout();
  window.addEventListener('resize', () => { layout(); drawReply(); });
}

function layout() {
  const box = el.seats.getBoundingClientRect();
  const cx = box.width / 2;
  const cy = box.height / 2;
  const rx = Math.max(150, box.width * 0.355);
  const ry = Math.max(105, box.height * 0.41);
  geo = { cx, cy, rx, ry };

  DEMO.seats.forEach((seat, i) => {
    // 整圈错开半步：不让任何一个座位正好落在吊灯底下（灯在正上方）
    const angle = (-90 + (i + 0.5) * (360 / DEMO.seats.length)) * Math.PI / 180;
    const node = seatNodes.get(seat.id);
    const sin = Math.sin(angle);
    // 上半个圈往外让：躲开桌子边缘和吊灯；下半个圈收进来：给底下的发言面板让位
    node.style.left = `${cx + rx * Math.cos(angle)}px`;
    node.style.top = `${cy + ry * sin * (sin < 0 ? 1.14 : 0.70)}px`;
    // 近桌那两位整体抬高一点，顺便只留名字（职责那行放不下）
    const isBottom = sin > 0.5;
    node.classList.toggle('bottom', isBottom);
    if (isBottom) node.style.top = `${parseFloat(node.style.top) - 30}px`;
  });

  el.replies.setAttribute('viewBox', `0 0 ${box.width} ${box.height}`);
}

/* ── 入场：灯亮、桌子推上来、人一个一个坐下 ─────────── */
function enter() {
  started = true;
  el.hint.textContent = '点一下继续';
  el.table.classList.add('in');
  DEMO.seats.forEach((seat, i) => {
    setTimeout(() => seatNodes.get(seat.id).classList.add('in'), 90 + i * 80);
  });
  setTimeout(next, 90 + DEMO.seats.length * 80 + 240);
}

/* ── 推进 ───────────────────────────────────────────── */
function next() {
  if (!started) { enter(); return; }
  if (index >= DEMO.turns.length - 1) {
    el.hint.textContent = '最后一条了，← 可回看';
    return;
  }
  index += 1;
  render(DEMO.turns[index], true);
}

function back() {
  if (!started || index <= 0) return;
  index -= 1;
  rebuildPot();
  render(DEMO.turns[index], false);
  el.hint.textContent = '点一下继续';
}

/* 底池：一条发言丢一枚筹码进去 */
function rebuildPot() {
  el.potChips.innerHTML = '';
  for (let i = 0; i <= index; i += 1) {
    const chip = document.createElement('i');
    const face = DEMO.turns[i].face;
    if (face === 'yin') chip.className = 'cool';
    el.potChips.appendChild(chip);
  }
}

/* 把一条发言画出来：谁、什么面、回谁、说了什么。 */
function render(turn, animate) {
  clearTimeout(revealTimer);

  el.counter.textContent = `第 ${index + 1} / ${DEMO.turns.length} 条`;
  el.platePhase.textContent = PHASE_TEXT[turn.phase] || turn.phase || '交锋';
  const phaseIndex = phaseOrder.indexOf(turn.phase);
  el.plateSeal.textContent = SEAL_NUM[phaseIndex >= 0 ? phaseIndex : 0];
  if (animate) {
    rebuildPot();
  }

  const isHost = turn.speaker_id === 'moderator';
  el.voiceover.classList.toggle('active', isHost);
  el.dealer.classList.toggle('active', isHost);

  // 只有说话的那个人亮，其余压暗
  for (const [id, node] of seatNodes) {
    node.classList.toggle('speaking', !isHost && id === turn.speaker_id);
    node.classList.toggle('dim', isHost || id !== turn.speaker_id);
  }

  // 整屋色温跟着这个人的面走；翻面时他面前那张暗牌也翻过来
  if (!isHost && turn.face) {
    document.body.dataset.face = turn.face;
    const node = seatNodes.get(turn.speaker_id);
    node.dataset.face = turn.face;
    node.querySelector('.card').classList.toggle('flipped', turn.face === 'yin');
  }

  el.who.textContent = isHost ? '荷官' : turn.speaker_name;
  el.faceChip.textContent = turn.face ? FACE_TEXT[turn.face] : '';
  el.faceChip.dataset.face = turn.face || '';
  el.intentChip.textContent = INTENT_TEXT[turn.intent] || turn.intent || '';

  const target = replyTarget(turn);
  el.replyChip.textContent = target ? `回应 ${target.name}` : '';
  drawReply(turn, target);

  el.body.innerHTML = '';
  const nodes = splitSentences(turn.content).map((text) => {
    const p = document.createElement('span');
    p.className = 'sent';
    p.innerHTML = highlight(text);
    el.body.appendChild(p);
    return p;
  });
  el.body.scrollTop = 0;
  el.speech.classList.add('in');

  if (!animate) {
    nodes.forEach((n) => n.classList.add('in'));
    el.wave.classList.remove('on');
    return;
  }

  const step = Math.max(70, Math.min(220, Math.round(1100 / Math.max(1, nodes.length))));
  el.wave.classList.add('on');
  nodes.forEach((node, i) => {
    revealTimer = setTimeout(() => {
      node.classList.add('in');
      if (i === nodes.length - 1) el.wave.classList.remove('on');
    }, i * step);
  });
}

function splitSentences(text) {
  const parts = text.match(/[^。！？!?…]+[。！？!?…]*/g) || [text];
  return parts.map((s) => s.trim()).filter(Boolean);
}

/* 置信度着色：让人一眼看出哪句是实的、哪句是听来的、哪句是猜的。 */
const CONF_RE = /(我知道|我确定|我敢肯定|确定的是)|(我听说|听说|印象里|听人说)|(我猜|我觉得|八成|多半|估摸着|估摸)/g;

function highlight(text) {
  const escaped = text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  return escaped.replace(CONF_RE, (match, solid, heard) => {
    const cls = solid ? 'c-solid' : heard ? 'c-heard' : 'c-guess';
    return `<b class="${cls}">${match}</b>`;
  });
}

/* 这条在回谁：支持 event_id、席位 id、席位名字三种写法。 */
function replyTarget(turn) {
  const raw = turn.replies_to;
  if (!raw) return null;
  const asEvent = /^event-(\d+)$/.exec(String(raw));
  if (asEvent) {
    const hit = DEMO.turns[Number(asEvent[1])];
    if (hit && hit !== turn) return { id: hit.speaker_id, name: hit.speaker_name };
    return null;
  }
  const seat = DEMO.seats.find((s) => s.name === raw) || DEMO.seats.find((s) => s.id === raw);
  return seat ? { id: seat.id, name: seat.name } : null;
}

function drawReply(turn = DEMO.turns[index], target = turn ? replyTarget(turn) : null) {
  if (!turn || !target) { el.replies.innerHTML = ''; return; }
  const from = seatNodes.get(turn.speaker_id);
  const to = seatNodes.get(target.id);
  if (!from || !to) { el.replies.innerHTML = ''; return; }

  const f = from.getBoundingClientRect();
  const t = to.getBoundingClientRect();
  const box = el.seats.getBoundingClientRect();
  const x1 = f.left - box.left + f.width / 2;
  const y1 = f.top - box.top + 32;
  const x2 = t.left - box.left + t.width / 2;
  const y2 = t.top - box.top + 32;

  const mx = (x1 + x2) / 2;
  const my = (y1 + y2) / 2;
  const cxp = mx + (mx - geo.cx) * 0.18;
  const cyp = my + (my - geo.cy) * 0.18;

  const cool = turn.face === 'yin' ? ' cool' : '';
  el.replies.innerHTML = `<path class="${cool}" d="M ${x1} ${y1} Q ${cxp} ${cyp} ${x2} ${y2}" />`;
}

/* ── 输入：点一下 / 空格走一条，← 回看 ─────────────── */
document.addEventListener('click', (event) => {
  if (event.target.closest('.notice')) return;
  next();
});

document.addEventListener('keydown', (event) => {
  if ([' ', 'Enter', 'ArrowRight', 'ArrowDown'].includes(event.key)) {
    event.preventDefault();
    next();
  } else if (['ArrowLeft', 'ArrowUp'].includes(event.key)) {
    event.preventDefault();
    back();
  }
});

boot();

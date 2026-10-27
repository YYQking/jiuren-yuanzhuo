/* S1「剧场夜」的交互：点一次走一条，绝不自动播放。
   原型只演示手感，数据是死的（data.js），不联网、不调模型。

   Qt 落地备忘：
   - 席位定位＝算好像素坐标后 setGeometry，窗口 resize 时重算（同这里的 layout()）
   - 逐句浮现＝QTimer 逐句 append 到只读 QTextEdit，或给每句做一个淡入的 QLabel
   - 光环/聚光＝QGraphicsDropShadowEffect（color + blurRadius）
   - 回应连线＝自绘 QWidget 的 paintEvent 画 QPainterPath（同这里的 SVG path）
*/

const DEMO = window.DEMO;

const el = {
  stage: document.getElementById('stage'),
  topic: document.getElementById('topic'),
  tableName: document.getElementById('tableName'),
  counter: document.getElementById('counter'),
  hint: document.getElementById('hint'),
  voiceover: document.getElementById('voiceover'),
  table: document.getElementById('table'),
  platePhase: document.getElementById('platePhase'),
  plateCount: document.getElementById('plateCount'),
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

let index = -1;          // 当前说到第几条（-1 = 还没开始）
let started = false;
let revealTimer = null;
let seatNodes = new Map();   // role_id -> element
let faceOf = new Map();      // role_id -> 这个人现在在哪个面
let geo = { rx: 0, ry: 0, cx: 0, cy: 0 };

/* ── 起手：铺好桌子和席位 ───────────────────────────── */
function boot() {
  el.topic.textContent = DEMO.topic;
  el.tableName.textContent = DEMO.section_label;
  el.plateCount.textContent = `${DEMO.seats.length} 人围坐`;
  el.counter.textContent = `第 0 / ${DEMO.turns.length} 条`;

  for (const seat of DEMO.seats) {
    const node = document.createElement('div');
    node.className = 'seat';
    node.dataset.face = 'yang';
    node.innerHTML = `
      <div class="seat-face"><img src="../assets/avatars/${seat.id}.svg" alt=""></div>
      <span class="seat-name">${seat.name}</span>
      <span class="seat-duty">${seat.duty}</span>
      <span class="seat-trigram">${seat.trigram}</span>`;
    node.title = `${seat.name}（${seat.trigram}）\n阳面：${seat.yang}\n阴面：${seat.yin}\n\n${seat.duty}`;
    el.seats.appendChild(node);
    seatNodes.set(seat.id, node);
    faceOf.set(seat.id, 'yang');
  }

  layout();
  window.addEventListener('resize', () => { layout(); drawReply(); });
}

/* 八个席位围着一圈。改窗口大小要重算，否则会错位。 */
function layout() {
  const box = el.seats.getBoundingClientRect();
  const cx = box.width / 2;
  const cy = box.height / 2;
  const rx = Math.max(160, box.width * 0.36);
  const ry = Math.max(110, box.height * 0.42);
  geo = { cx, cy, rx, ry, w: box.width, h: box.height };

  DEMO.seats.forEach((seat, i) => {
    const angle = (-90 + i * (360 / DEMO.seats.length)) * Math.PI / 180;
    const x = cx + rx * Math.cos(angle);
    const y = cy + ry * Math.sin(angle);
    const node = seatNodes.get(seat.id);
    node.style.left = `${x}px`;
    node.style.top = `${y}px`;
    node.dataset.angle = angle;
  });

  el.replies.setAttribute('viewBox', `0 0 ${box.width} ${box.height}`);
}

/* ── 入场：灯亮、桌子推上来、人一个一个坐下 ─────────── */
function enter() {
  started = true;
  el.hint.textContent = '点一下继续';
  el.table.classList.add('in');
  DEMO.seats.forEach((seat, i) => {
    setTimeout(() => seatNodes.get(seat.id).classList.add('in'), 90 + i * 85);
  });
  setTimeout(next, 90 + DEMO.seats.length * 85 + 260);
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
  render(DEMO.turns[index], false);
  el.hint.textContent = '点一下继续';
}

/* 把一条发言画出来：谁、什么面、回谁、说了什么。 */
function render(turn, animate) {
  clearTimeout(revealTimer);

  el.counter.textContent = `第 ${index + 1} / ${DEMO.turns.length} 条`;
  el.platePhase.textContent = turn.phase || '讨论中';

  // 主持人不在桌上：灯打在"画外音"那一条上
  const isHost = turn.speaker_id === 'moderator';
  el.voiceover.classList.toggle('active', isHost);

  // 谁在说：只有他亮
  for (const [id, node] of seatNodes) {
    node.classList.toggle('speaking', !isHost && id === turn.speaker_id);
    node.classList.toggle('dim', !isHost ? id !== turn.speaker_id : true);
  }

  // 整屋色温跟着这个人的面走（翻面最直观的体现）
  if (!isHost && turn.face) {
    document.body.dataset.face = turn.face;
    el.seats.parentElement.dataset.face = turn.face;
    faceOf.set(turn.speaker_id, turn.face);
    seatNodes.get(turn.speaker_id).dataset.face = turn.face;
  }

  el.who.textContent = isHost ? '主持人' : turn.speaker_name;
  el.faceChip.textContent = turn.face ? FACE_TEXT[turn.face] : '';
  el.faceChip.dataset.face = turn.face || '';
  el.intentChip.textContent = INTENT_TEXT[turn.intent] || turn.intent || '';

  const target = replyTarget(turn);
  el.replyChip.textContent = target ? `回应 ${target.name}` : '';
  drawReply(turn, target);

  // 正文：按句切开，一句一句出现
  el.body.innerHTML = '';
  const sentences = splitSentences(turn.content);
  const nodes = sentences.map((text) => {
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

  // 语速：整段控制在 1 秒上下，太长就一次多放几句
  const step = Math.max(70, Math.min(220, Math.round(1100 / Math.max(1, nodes.length))));
  el.wave.classList.add('on');
  nodes.forEach((node, i) => {
    revealTimer = setTimeout(() => {
      node.classList.add('in');
      if (i === nodes.length - 1) el.wave.classList.remove('on');
    }, i * step);
  });
}

/* 把一句话切成若干句（中文标点，保留标点）。 */
function splitSentences(text) {
  const parts = text.match(/[^。！？!?…]+[。！？!?…]*/g) || [text];
  return parts.map((s) => s.trim()).filter(Boolean);
}

/* 置信度着色：让人一眼看出哪句是实的、哪句是听来的、哪句是猜的。
   Qt 落地：同一段正则，写进 QTextEdit 的 HTML。 */
const CONF_RE = /(我知道|我确定|我敢肯定|确定的是)|(我听说|听说|印象里|听人说)|(我猜|我觉得|八成|多半|估摸着|估摸)/g;

function highlight(text) {
  const escaped = text
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  return escaped.replace(CONF_RE, (match, solid, heard, guess) => {
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
    if (hit && hit !== turn) return { id: hit.speaker_id, name: hit.speaker_name, index: Number(asEvent[1]) };
    return null;
  }
  const byName = DEMO.seats.find((s) => s.name === raw);
  const byId = DEMO.seats.find((s) => s.id === raw);
  const seat = byName || byId;
  if (!seat) return null;
  return { id: seat.id, name: seat.name, index: -1 };
}

/* 一条细线，从说话的人连到被他回应的人。 */
function drawReply(turn = DEMO.turns[index], target = turn ? replyTarget(turn) : null) {
  if (!turn || !target) { el.replies.innerHTML = ''; return; }
  const from = seatNodes.get(turn.speaker_id);
  const to = seatNodes.get(target.id);
  if (!from || !to) { el.replies.innerHTML = ''; return; }

  const f = from.getBoundingClientRect();
  const t = to.getBoundingClientRect();
  const box = el.seats.getBoundingClientRect();
  const x1 = f.left - box.left + f.width / 2;
  const y1 = f.top - box.top + 34;
  const x2 = t.left - box.left + t.width / 2;
  const y2 = t.top - box.top + 34;

  // 控制点往外推一点，线就从桌子外侧绕过去
  const mx = (x1 + x2) / 2;
  const my = (y1 + y2) / 2;
  const push = 0.18;
  const cxp = mx + (mx - geo.cx) * push;
  const cyp = my + (my - geo.cy) * push;

  const cool = turn.face === 'yin' ? ' cool' : '';
  el.replies.innerHTML =
    `<path class="${cool}" d="M ${x1} ${y1} Q ${cxp} ${cyp} ${x2} ${y2}" />`;
}

/* ── 输入：点一下 / 空格走一条，← 回看 ─────────────── */
document.addEventListener('click', (event) => {
  if (event.target.closest('.notice')) return;
  next();
});

document.addEventListener('keydown', (event) => {
  if (event.key === ' ' || event.key === 'Enter' || event.key === 'ArrowRight' || event.key === 'ArrowDown') {
    event.preventDefault();
    next();
  } else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') {
    event.preventDefault();
    back();
  }
});

boot();

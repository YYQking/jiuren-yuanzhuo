/* 方案 A 的脚本：一个对话框，三段对白。
   1) 荷官问你今晚聊什么  → 选桌
   2) 他追问一句具体的    → 写议题
   3) 他确认一遍          → 开桌  */

const $ = (s) => document.querySelector(s);

const SEATS = {
  event: ['qian', 'kun', 'zhen', 'xun', 'kan', 'li', 'gen', 'dui'],
  business: ['trend', 'industry', 'builder', 'technology', 'need', 'bystander', 'researcher', 'creative', 'skeptic'],
};

const state = { mode: null, topic: '' };

/* 远处桌上先摆座位影子（默认八人） */
function seatShadows(n) {
  const holder = $('#ftSeats');
  holder.innerHTML = '';
  for (let i = 0; i < n; i += 1) {
    const a = (-90 + (i + 0.5) * (360 / n)) * Math.PI / 180;
    const d = document.createElement('i');
    d.style.left = `${50 + 44 * Math.cos(a)}%`;
    d.style.top = `${50 + 40 * Math.sin(a)}%`;
    holder.appendChild(d);
  }
}
seatShadows(8);

/* 打字机：一个字一个字出，点一下可以直接出完 */
const typer = {
  timer: 0,
  full: '',
  done: true,
  type(text, onDone) {
    clearInterval(this.timer);
    this.full = text;
    this.done = false;
    const el = $('#say');
    let i = 0;
    el.innerHTML = '<span class="caret"></span>';
    this.timer = setInterval(() => {
      i += 1;
      el.innerHTML = `${text.slice(0, i)}<span class="caret"></span>`;
      if (i >= text.length) {
        clearInterval(this.timer);
        el.textContent = text;
        this.done = true;
        if (onDone) onDone();
      }
    }, 26);
  },
  finish() {
    clearInterval(this.timer);
    $('#say').textContent = this.full;
    this.done = true;
  },
};

function clearChoices() {
  $('#choices').innerHTML = '';
  $('#writeBox').hidden = true;
}

function addChoice(label, note, onClick) {
  const b = document.createElement('button');
  b.type = 'button';
  b.className = 'choice';
  b.innerHTML = `<b>${label}</b><small>${note}</small>`;
  b.addEventListener('click', (e) => {
    e.stopPropagation();
    onClick();
  });
  $('#choices').appendChild(b);
  return b;
}

/* ── 第一段：选桌 ─────────────────────────────────── */
function step1() {
  clearChoices();
  typer.type('来了。今晚想在哪张桌上坐坐？——一张谈生意，一张聊人事。');
  addChoice('八卦桌', '八个人，各有各的脾气', () => {
    state.mode = 'event';
    seatShadows(8);
    step2();
  });
  addChoice('商业痛点桌', '九个人，盯一件事能不能做成', () => {
    state.mode = 'business';
    seatShadows(9);
    step2();
  });
  addChoice('我不知道，从今天的新闻里挑', '随机给你一条热点', () => {
    state.mode = 'event';
    seatShadows(8);
    clearChoices();
    typer.type('行，那就抓一条今天的。正好有人在吵物业把车位转租出去的事。');
    setTimeout(() => {
      $('#topicInput').value = '某小区物业把业主的固定车位转租给了外面的人，业主群吵了一整天';
      step3();
    }, 1200);
  });
}

/* ── 第二段：写议题 ───────────────────────────────── */
function step2() {
  clearChoices();
  typer.type(state.mode === 'event'
    ? '八卦桌上不聊大道理，得有一件具体的、有人在吵的事。说一件。'
    : '商业这张桌只认具体的事：谁在什么时候、被什么为难住了。说一件。');
  $('#writeBox').hidden = false;
  $('#topicInput').value = '';
  $('#topicInput').focus();
}

function step3() {
  clearChoices();
  const topic = ($('#topicInput').value || '').trim();
  state.topic = topic;
  if (!topic) {
    typer.type('空着可不行。哪怕一句大白话，也得有个人、有个地方、有件让他难受的事。');
    step2();
    return;
  }
  const who = state.mode === 'event' ? '八个人已经坐下了' : '九个人已经坐下了';
  typer.type(`记下了。「${topic}」——${who}，就等你翻牌。`);
  addChoice('开桌', '进到桌子那页', () => {
    window.location.href = 'index.html';
  });
  addChoice('我再改改这个话题', '回去重写', () => step2());
}

$('#okBtn').addEventListener('click', (e) => {
  e.stopPropagation();
  step3();
});

$('#topicInput').addEventListener('keydown', (e) => {
  if (e.key === 'Enter') step3();
  e.stopPropagation();
});

/* 空白处点一下：把正在打的字直接出完 */
document.addEventListener('click', () => {
  if (!typer.done) typer.finish();
});

document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') window.location.href = 'lobby-options.html';
});

step1();

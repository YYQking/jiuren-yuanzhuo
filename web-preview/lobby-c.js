/* 方案 C 的脚本：点桌 → 推近 → 写议题 → 开桌。 */

const $ = (s) => document.querySelector(s);

const NAMES = {
  event: ['乾明', '坤兰', '震山', '巽竹', '坎川', '离霞', '艮石', '兑溪'],
  business: ['趋势分析师', '行业从业者', '创业实践者', '技术与实现顾问', '真实需求者',
    '普通路人', '用户研究员', '跨界创意者', '怀疑者'],
};

/* 每张桌周围摆座位点：桌是椭圆，点按角度排；推近之后再加名字 */
document.querySelectorAll('.tbl').forEach((tbl) => {
  const holder = tbl.querySelector('.tbl-seats');
  const n = Number(tbl.dataset.count);
  const names = NAMES[tbl.dataset.mode] || [];
  tbl.querySelector('.tbl-core').textContent = `${tbl.dataset.name} · ${n} 人`;
  holder.innerHTML = '';
  for (let i = 0; i < n; i += 1) {
    const a = (-90 + (i + 0.5) * (360 / n)) * Math.PI / 180;
    const dot = document.createElement('i');
    dot.style.left = `${50 + 46 * Math.cos(a)}%`;
    dot.style.top = `${50 + 44 * Math.sin(a)}%`;
    holder.appendChild(dot);

    const label = document.createElement('b');
    label.className = 'tbl-name';
    label.textContent = names[i] || '';
    label.style.left = `${50 + 57 * Math.cos(a)}%`;
    label.style.top = `${50 + 55 * Math.sin(a)}%`;
    holder.appendChild(label);
  }
});

document.querySelectorAll('.tbl').forEach((tbl) => {
  tbl.addEventListener('click', () => {
    document.querySelector('.plan').classList.add('zoomed');
    document.querySelectorAll('.tbl').forEach((t) => t.classList.toggle('is-picked', t === tbl));
    $('#note').hidden = false;
    $('#noteWho').textContent = `${tbl.dataset.name} · ${tbl.dataset.count} 人`;
    $('#noteInput').focus();
  });
});

$('#backBtn').addEventListener('click', () => {
  document.querySelector('.plan').classList.remove('zoomed');
  document.querySelectorAll('.tbl').forEach((t) => t.classList.remove('is-picked'));
  $('#note').hidden = true;
});

$('#startBtn').addEventListener('click', () => {
  if (!$('#noteInput').value.trim()) {
    $('#noteInput').focus();
    return;
  }
  window.location.href = 'index.html';
});

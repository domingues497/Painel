/* Painel Zabbix — cards nunca ficam por cima de outros: empurram e reordenam (estilo Sortable).
   Retângulos: {x, y, w, h} em px, relativos ao mesmo container.
   Usado pelos motores de arrastar/redimensionar (freeCardLayout e TOPs de hosts.html). */
(function () {
  "use strict";
  const GAP = 12;   // folga ao reposicionar um card que colidiu
  const EPS = 0.5;  // bordas encostadas NÃO contam como sobreposição

  const overlaps = (a, b) =>
    a.x < b.x + b.w - EPS && a.x + a.w > b.x + EPS &&
    a.y < b.y + b.h - EPS && a.y + a.h > b.y + EPS;

  const collides = (rect, others) => others.some(o => overlaps(rect, o));

  // Durante o arraste: tenta a posição desejada; se bater, "desliza" num eixo; senão fica onde estava.
  function constrainMove(prev, wanted, size, others) {
    const test = (x, y) => !collides({ x, y, w: size.w, h: size.h }, others);
    if (test(wanted.x, wanted.y)) return { x: wanted.x, y: wanted.y };
    if (test(wanted.x, prev.y)) return { x: wanted.x, y: prev.y };
    if (test(prev.x, wanted.y)) return { x: prev.x, y: wanted.y };
    return { x: prev.x, y: prev.y };
  }

  // Layout salvo/inicial/duplicado: empurra o card para baixo até achar espaço livre.
  function resolve(rect, others, maxW) {
    let x = Math.max(0, rect.x), y = Math.max(0, rect.y);
    if (maxW) x = Math.max(0, Math.min(x, maxW - rect.w));
    for (let i = 0; i < 500; i++) {
      const hit = others.filter(o => overlaps({ x, y, w: rect.w, h: rect.h }, o));
      if (!hit.length) break;
      y = Math.max(...hit.map(o => o.y + o.h)) + GAP;
    }
    return { x, y };
  }

  // Estilo Sortable (1): `fixed` é o card em movimento; os demais, vindos SEMPRE da posição inicial do gesto,
  // são empurrados para baixo em cascata. Retorna [{x,y}] na mesma ordem de `list`.
  function push(fixed, list) {
    const order = list.map((_, i) => i).sort((a, b) => list[a].y - list[b].y || list[a].x - list[b].x);
    const placed = [fixed], out = new Array(list.length);
    for (const i of order) {
      const o = list[i], pos = resolve(o, placed);
      out[i] = pos; placed.push({ x: pos.x, y: pos.y, w: o.w, h: o.h });
    }
    return out;
  }

  // Estilo Sortable (2): ao soltar, cada card sobe até o primeiro espaço livre, preenchendo os vazios.
  function compact(list) {
    const order = list.map((_, i) => i).sort((a, b) => list[a].y - list[b].y || list[a].x - list[b].x);
    const placed = [], out = new Array(list.length);
    for (const i of order) {
      const o = list[i];
      let y = 0;
      for (let k = 0; k < 500; k++) {
        const hit = placed.filter(q => overlaps({ x: o.x, y, w: o.w, h: o.h }, { x: q.x, y: q.y, w: q.w, h: q.h + GAP }));
        if (!hit.length) break;
        y = Math.max(...hit.map(q => q.y + q.h + GAP));
      }
      out[i] = { x: o.x, y }; placed.push({ x: o.x, y, w: o.w, h: o.h });
    }
    return out;
  }

  // Ordem visual (linha por linha, esquerda -> direita), tolerando pequenas diferenças de y entre cards da mesma linha.
  function visualOrder(list, band) {
    const b = Math.max(40, band || 80);
    return list.map((_, i) => i).sort((i, j) => Math.round(list[i].y / b) - Math.round(list[j].y / b) || list[i].x - list[j].x);
  }

  // Grade alinhada: `n` cards por linha, todos com a mesma largura (preenche `width`).
  // Cada linha assume a altura do card mais alto dela, então as bordas ficam alinhadas.
  function gridLayout(list, n, width, gap) {
    const cw = Math.max(1, Math.floor((width - gap * (n - 1)) / n)), out = new Array(list.length);
    const avgH = list.reduce((sum, o) => sum + o.h, 0) / (list.length || 1);
    const order = visualOrder(list, avgH / 2);
    let y = 0;
    for (let start = 0; start < order.length; start += n) {
      const row = order.slice(start, start + n);
      const rowH = Math.max(...row.map(idx => list[idx].h));
      row.forEach((idx, col) => { out[idx] = { x: col * (cw + gap), y, w: cw, h: rowH }; });
      y += rowH + gap;
    }
    return out;
  }

  // Mesmo tamanho: mantém a ordem visual e empurra para baixo o que colidir. `list` já traz os novos w/h.
  function flow(list, maxW) {
    const placed = [], out = new Array(list.length);
    visualOrder(list, list[0] ? list[0].h / 2 : 80).forEach(idx => {
      const o = list[idx], pos = resolve(o, placed, maxW);
      out[idx] = pos; placed.push({ x: pos.x, y: pos.y, w: o.w, h: o.h });
    });
    return out;
  }

  window.PanelNoOverlap = { visualOrder, gridLayout, flow, overlaps, collides, constrainMove, resolve, push, compact };
})();

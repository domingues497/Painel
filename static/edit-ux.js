/* Painel Zabbix — UX do modo de edição: avisos com "Desfazer" e barra de ajuda fixa.
   Expõe window.PanelUX.toast(mensagem, { action, onAction, ms }). */
(function () {
  "use strict";
  let toastEl = null, timer = null;

  function toast(message, opts) {
    const { action, onAction, ms = 7000 } = opts || {};
    if (!toastEl) {
      toastEl = document.createElement("div");
      toastEl.className = "ux-toast";
      toastEl.setAttribute("role", "status");
      toastEl.setAttribute("aria-live", "polite");
      document.body.appendChild(toastEl);
    }
    clearTimeout(timer);
    toastEl.replaceChildren();
    const text = document.createElement("span");
    text.textContent = message;
    toastEl.appendChild(text);
    if (action) {
      const btn = document.createElement("button");
      btn.type = "button"; btn.textContent = action;
      btn.addEventListener("click", () => { toastEl.classList.remove("show"); clearTimeout(timer); if (onAction) onAction(); });
      toastEl.appendChild(btn);
    }
    toastEl.classList.add("show");
    timer = setTimeout(() => toastEl.classList.remove("show"), ms);
  }

  // Assistente de padronização: oferece "mesmo tamanho" e "N cards por linha" (grade alinhada) após redimensionar.
  let suggestEl = null, suggestTimer = null;
  function closeSuggest() {
    clearTimeout(suggestTimer);
    if (suggestEl) { suggestEl.remove(); suggestEl = null; }
    document.removeEventListener("keydown", onSuggestKey);
  }
  function onSuggestKey(e) { if (e.key === "Escape") closeSuggest(); }
  function suggestLayout(opts) {
    const { count, sizeLabel, maxPerRow = 4, tightFrom = Infinity, minOk = () => true, onSameSize, onGrid } = opts;
    closeSuggest();
    const box = suggestEl = document.createElement("div");
    box.className = "ux-suggest";
    box.setAttribute("role", "dialog");
    box.setAttribute("aria-label", "Padronizar cards");
    const title = document.createElement("strong");
    title.textContent = `Padronizar os ${count} cards deste grupo?`;
    const same = document.createElement("button");
    same.type = "button"; same.className = "primary"; same.textContent = `Mesmo tamanho (${sizeLabel})`;
    same.addEventListener("click", () => { closeSuggest(); onSameSize(); });
    const rowLabel = document.createElement("span");
    rowLabel.textContent = "Alinhar em grade, cards por linha:";
    const chips = document.createElement("span");
    chips.className = "ux-chips";
    for (let n = 1; n <= maxPerRow; n++) {
      const chip = document.createElement("button");
      chip.type = "button"; chip.textContent = String(n);
      chip.setAttribute("aria-label", `${n} ${n === 1 ? "card" : "cards"} por linha`);
      if (!minOk(n)) { chip.disabled = true; chip.title = "Largura insuficiente para esta quantidade por linha"; }
      else if (n >= tightFrom) { chip.className = "tight"; chip.title = "Cards ficarão mais estreitos que o mínimo padrão"; }
      chip.addEventListener("click", () => { closeSuggest(); onGrid(n); });
      chips.appendChild(chip);
    }
    const no = document.createElement("button");
    no.type = "button"; no.className = "ux-dismiss"; no.textContent = "Agora não";
    no.addEventListener("click", closeSuggest);
    box.append(title, same, rowLabel, chips, no);
    document.body.appendChild(box);
    document.addEventListener("keydown", onSuggestKey);
    suggestTimer = setTimeout(closeSuggest, 20000);
  }

  // Barra fixa (só aparece em modo edição): lembra os gestos e oferece "Concluir" sem precisar rolar até o topo.
  function buildBar() {
    if (document.querySelector(".edit-bar")) return;
    const bar = document.createElement("div");
    bar.className = "edit-bar";
    bar.setAttribute("role", "region");
    bar.setAttribute("aria-label", "Modo de edição do painel");
    bar.innerHTML = '<strong>Modo de edição</strong>' +
      '<span>Arraste pelo título ou pelo ⠿</span><span>✎ Renomear</span><span>× Excluir</span><span>Canto inferior direito: redimensionar</span>';
    const done = document.createElement("button");
    done.type = "button"; done.className = "primary"; done.textContent = "Concluir";
    done.addEventListener("click", () => document.querySelector(".layout-edit-toggle[aria-pressed]")?.click());
    bar.appendChild(done);
    document.body.appendChild(bar);
  }

  window.PanelUX = { toast, suggestLayout };
  // A barra só aparece com body.layout-edit-active (CSS), então pode ser criada sempre; o botão é buscado no clique.
  if (document.body) buildBar(); else document.addEventListener("DOMContentLoaded", buildBar);
})();

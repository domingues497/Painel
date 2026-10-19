// Revela os itens restritos do menu (Executivo / Configuração) após 5 cliques
// no texto "Atualizado às ...". O desbloqueio fica salvo neste navegador.
(function () {
  const STORAGE_KEY = "painel.adminNav";
  const NEEDED = 5;
  const WINDOW_MS = 2000;
  let clicks = 0;
  let lastClick = 0;

  const unlock = () => {
    document.body.classList.add("nav-admin-unlocked");
    try { localStorage.setItem(STORAGE_KEY, "1"); } catch (e) {}
  };

  try {
    if (localStorage.getItem(STORAGE_KEY) === "1") document.body.classList.add("nav-admin-unlocked");
  } catch (e) {}

  const target = document.getElementById("updated");
  if (target) {
    target.addEventListener("click", () => {
      const now = Date.now();
      if (now - lastClick > WINDOW_MS) clicks = 0;
      lastClick = now;
      if (++clicks >= NEEDED) { clicks = 0; unlock(); }
    });
  }
})();

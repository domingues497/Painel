/* Painel Zabbix — cálculos dos cards TOP 10 (funções puras, sem DOM).
   window.RankCalc.stats(valores) -> { n, sum, avg, median, p95, min, max, range, std } | null
   window.RankCalc.toTSV(linhas, formatar, stats, formatarStat) -> texto para colar em planilha. */
(function () {
  "use strict";

  // Percentil por interpolação linear (p entre 0 e 1) sobre valores já ordenados.
  function percentile(sorted, p) {
    if (sorted.length === 1) return sorted[0];
    const pos = (sorted.length - 1) * p, lo = Math.floor(pos), hi = Math.ceil(pos);
    return sorted[lo] + (sorted[hi] - sorted[lo]) * (pos - lo);
  }

  function stats(values) {
    const v = values.filter(Number.isFinite).sort((a, b) => a - b);
    const n = v.length;
    if (!n) return null;
    const sum = v.reduce((acc, x) => acc + x, 0), avg = sum / n;
    // Desvio padrão amostral (n-1); com um único valor é 0.
    const std = n > 1 ? Math.sqrt(v.reduce((acc, x) => acc + (x - avg) ** 2, 0) / (n - 1)) : 0;
    return { n, sum, avg, median: percentile(v, 0.5), p95: percentile(v, 0.95), min: v[0], max: v[n - 1], range: v[n - 1] - v[0], std };
  }

  // Texto separado por TAB (cola direto no Excel/Sheets): tabela de linhas + bloco de estatísticas.
  function toTSV(rows, fmtValue, st, fmtStat) {
    const lines = ["#\tHost\tValor"];
    rows.forEach((r, i) => lines.push(`${i + 1}\t${r.host.name}\t${fmtValue(r.value, r)}`));
    if (st) {
      lines.push("", "Estatística\tValor");
      for (const [label, value] of fmtStat(st)) lines.push(`${label}\t${value}`);
    }
    return lines.join("\n");
  }

  window.RankCalc = { stats, percentile, toTSV };
})();

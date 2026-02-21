async function loadData() {
  const res = await fetch("data/processed/level_recommendations.json");
  if (!res.ok) throw new Error("JSON 로드 실패");
  return res.json();
}

function render(level, data) {
  const items = data.levels[level] || [];
  document.getElementById("summary").textContent = `${level} 추천 ${items.length}개`;
  document.getElementById("list").innerHTML = items.slice(0, 20).map((w) => {
    const examples = (w.examples_by_meaning || [])
      .flatMap((b) => b.examples || [])
      .slice(0, 3)
      .map((e) => `<li>${e}</li>`)
      .join("");

    return `<li>
      <strong>${w.lemma}</strong> <small>(${w.pos || "unknown"})</small>
      <div>• ${w.meaning_1 || "-"}${w.meaning_1_ko ? ` <em>(${w.meaning_1_ko})</em>` : ""}</div>
      ${w.meaning_2 ? `<div>• ${w.meaning_2}${w.meaning_2_ko ? ` <em>(${w.meaning_2_ko})</em>` : ""}</div>` : ""}
      <ul>${examples}</ul>
    </li>`;
  }).join("");
}

let cached;
async function run() {
  if (!cached) cached = await loadData();
  const level = document.getElementById("level-select").value;
  render(level, cached);
}

document.getElementById("load-btn").addEventListener("click", run);
run();

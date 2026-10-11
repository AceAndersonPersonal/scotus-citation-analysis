"use strict";
const $ = id => document.getElementById(id);
let dataset, activeTerm, selectedCase;
function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}
function matches(item, query) {
  return `${item.name} ${item.citation}`.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase());
}
function renderCases() {
  const visible = activeTerm.sources.filter(item => matches(item, $("case-search").value));
  $("case-count").textContent = `${visible.length} of ${activeTerm.source_count} source cases`;
  $("case-list").replaceChildren();
  for (const item of visible) {
    const button = element("button", item.name, "case-option");
    button.type = "button";
    button.setAttribute("aria-pressed", String(item.id === selectedCase?.id));
    button.append(element("small", `${item.citation} · ${item.citations.length} cited cases`));
    button.addEventListener("click", () => { selectCase(item); $("case-title").focus({preventScroll: true}); });
    $("case-list").append(button);
  }
  if (!visible.length) $("case-list").append(element("p", "No matching source cases.", "empty"));
}
function renderCitations() {
  const visible = selectedCase.citations.filter(item => matches(item, $("citation-search").value));
  visible.sort((a,b) => {
    const difference = $("sort").value === "oldest" ? b.age-a.age : $("sort").value === "newest" ? a.age-b.age : 0;
    return difference || a.name.localeCompare(b.name) || a.id.localeCompare(b.id);
  });
  $("citations").replaceChildren();
  $("citation-status").textContent = `${visible.length} of ${selectedCase.citations.length} recorded links`;
  for (const item of visible) {
    const row = element("tr"), name = element("td"), link = element("a", item.name);
    link.href = item.url; link.target = "_blank"; link.rel = "noopener noreferrer";
    link.setAttribute("aria-label", `${item.name} — open opinion in a new tab`);
    name.append(link, element("small", item.citation));
    const age = element("td"); age.append(element("span", `${item.age} yr`, "age"));
    row.append(name, element("td", String(item.year)), age); $("citations").append(row);
  }
  $("empty-citations").hidden = visible.length > 0;
  $("empty-citations").textContent = selectedCase.citations.length ? "No matching precedents." : "No citation links are recorded for this source case. See the dataset review records for coverage details.";
}
function selectCase(item, updateUrl = true) {
  selectedCase = item;
  $("case-content").hidden = false; $("loading").hidden = true;
  $("case-term").textContent = `October term ${activeTerm.term} (${activeTerm.term}–${activeTerm.term + 1})`;
  $("case-title").textContent = item.name;
  $("case-meta").textContent = `${item.citation} · Decision date: ${item.date}`;
  $("opinion-link").href = item.url;
  $("citation-count").textContent = item.citations.length;
  $("median-age").textContent = item.median_age === null ? "—" : `${item.median_age} yr`;
  $("source-year").textContent = item.year;
  $("citation-search").value = "";
  $("term-coverage").textContent = `Term ${activeTerm.term}: ${activeTerm.source_count} source cases included; ${activeTerm.held_for_review} held for review; ${activeTerm.flagged_citations} flagged citation-review entries. Flagged entries are not a count of all missing citations.`;
  $("term-method").textContent = `${activeTerm.method} Review status: ${activeTerm.review_status}.`;
  if (updateUrl) {
    const params = new URLSearchParams({term: String(activeTerm.term), case: item.id});
    history.replaceState(null, "", `${location.pathname}?${params}`);
  }
  renderCases(); renderCitations();
}
function selectTerm(term, caseId, updateUrl = true) {
  activeTerm = term;
  $("case-search").value = ""; $("sort").value = "name";
  for (const button of $("terms").children) button.setAttribute("aria-pressed", String(Number(button.dataset.term) === term.term));
  const item = term.sources.find(item => item.id === caseId) || term.sources.find(item => /Leocal v\./i.test(item.name)) || term.sources[0];
  if (item) selectCase(item, updateUrl);
  else { selectedCase = null; $("case-content").hidden = true; $("loading").hidden = false; $("loading").textContent = "No source cases are available for this term."; renderCases(); }
}
async function initialize() {
  try {
    const response = await fetch("data.json");
    if (!response.ok) throw new Error("Dataset request failed");
    dataset = await response.json();
    if (dataset.schema_version !== 1 || !dataset.terms?.length) throw new Error("Unsupported dataset");
    $("term-range").textContent = dataset.terms.map(term => term.term).join(" / ");
    $("coverage-total").textContent = `${dataset.terms.reduce((n,t) => n+t.source_count,0)} source cases · ${dataset.terms.reduce((n,t) => n+t.edge_count,0).toLocaleString()} citation links`;
    for (const term of dataset.terms) {
      const button = element("button", String(term.term)); button.type = "button"; button.dataset.term = term.term;
      button.addEventListener("click", () => selectTerm(term)); $("terms").append(button);
    }
    function restoreSelection() {
      const params = new URLSearchParams(location.search);
      selectTerm(dataset.terms.find(term => String(term.term) === params.get("term")) || dataset.terms[0], params.get("case"), false);
    }
    restoreSelection(); window.addEventListener("popstate", restoreSelection);
    $("case-search").addEventListener("input", renderCases);
    $("citation-search").addEventListener("input", renderCitations);
    $("sort").addEventListener("change", renderCitations);
  } catch (error) {
    $("loading").textContent = "The citation data could not be loaded. Reload the page, or use the comparative report above.";
    $("term-range").textContent = "Data unavailable"; $("coverage-total").textContent = "The static report remains available.";
  }
}
initialize();

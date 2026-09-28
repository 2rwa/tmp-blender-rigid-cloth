(() => {
  const body = document.body;
  const assetRoot = body.dataset.assetRoot || "assets";
  const dataPath = body.dataset.dataPath || "data/experiments.json";
  const cardsEl = document.getElementById("cards");
  const template = document.getElementById("cardTemplate");
  const searchInput = document.getElementById("searchInput");
  const categoryFilter = document.getElementById("categoryFilter");
  const systemFilter = document.getElementById("systemFilter");
  const tagFilter = document.getElementById("tagFilter");
  const sortOrder = document.getElementById("sortOrder");
  const emptyState = document.getElementById("emptyState");
  const activeFilter = document.getElementById("activeFilter");

  let payload = null;

  const metricLabels = {
    first_tear_frame: "first tear",
    impact_frame: "impact",
    max_components: "components",
    max_vertices: "max vertices",
    duration_seconds: "duration",
    "movie.duration_seconds": "duration",
    "report.simulation_seconds": "simulation",
    "report.max_displacement": "max displacement",
    "report.jelly_max_displacement": "jelly displacement",
    "report.cloth_max_displacement": "cloth displacement",
    "report.rigid_body_count": "rigid bodies",
    "report.possible_proxy_tunneling": "proxy tunneling",
    tear_observed: "tear observed"
  };

  function formatMetric(key, value) {
    if (value === null || value === undefined) return "—";
    if (typeof value === "boolean") return value ? "yes" : "no";
    if (typeof value === "number") {
      if (key.includes("seconds")) return value.toFixed(value < 10 ? 2 : 1) + " s";
      return Number.isInteger(value) ? value.toLocaleString() : value.toFixed(4).replace(/0+$/, "").replace(/\.$/, "");
    }
    return String(value);
  }

  function option(select, value) {
    const o = document.createElement("option");
    o.value = value;
    o.textContent = value;
    select.appendChild(o);
  }

  function makeBadge(text, cls = "") {
    const span = document.createElement("span");
    span.className = "badge" + (cls ? " " + cls : "");
    span.textContent = text;
    return span;
  }

  function makeLink(text, href) {
    const a = document.createElement("a");
    a.textContent = text;
    a.href = href;
    return a;
  }

  function artifact(entry, kind) {
    return (entry.artifacts || []).find(a => a.kind === kind);
  }

  function buildMedia(entry) {
    const wrap = document.createElement("div");
    wrap.className = "media-wrap";
    const img = document.createElement("img");
    img.loading = "lazy";
    img.alt = entry.title + " preview";
    img.src = assetRoot + "/" + encodeURIComponent(entry.id) + "/preview.jpg";
    wrap.appendChild(img);

    if (artifact(entry, "video")) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "play";
      button.setAttribute("aria-label", "Play " + entry.title);
      button.textContent = "▶";
      button.addEventListener("click", () => {
        const video = document.createElement("video");
        video.controls = true;
        video.autoplay = true;
        video.playsInline = true;
        video.src = assetRoot + "/" + encodeURIComponent(entry.id) + "/media.mp4";
        wrap.replaceChildren(video);
      }, { once: true });
      wrap.appendChild(button);
    }
    return wrap;
  }

  function buildDetail(entry) {
    const frag = document.createDocumentFragment();
    const config = entry.config || {};
    const add = (k, v) => {
      if (v === null || v === undefined || v === "") return;
      const div = document.createElement("div");
      const key = document.createElement("span");
      const val = document.createElement("strong");
      key.textContent = k;
      val.textContent = Array.isArray(v) ? v.join(" × ") : String(v);
      div.append(key, val);
      frag.appendChild(div);
    };
    add("category", entry.category);
    add("series", entry.series);
    add("frames", config.frameEnd ? (String(config.frameStart || 1) + "–" + config.frameEnd) : null);
    add("fps", config.fps);
    add("renderer", config.renderer);
    add("resolution", config.resolution);

    const cloth = config.cloth || {};
    add("threshold", cloth.tearing_threshold);
    add("stretchiness", cloth.stretchiness);
    add("bendiness", cloth.bendiness);
    add("mass", cloth.mass);
    add("substeps", cloth.substeps);
    add("constraint steps", cloth.constraint_steps);

    const collider = config.collider || {};
    add("collider", collider.collider_type);
    add("radius", collider.radius);
    add("margin", collider.margin);
    return frag;
  }

  function buildCard(entry) {
    const node = template.content.firstElementChild.cloneNode(true);
    node.querySelector(".media").appendChild(buildMedia(entry));

    const badges = node.querySelector(".badges");
    badges.appendChild(makeBadge(entry.category, "category"));
    (entry.systems || []).forEach(s => badges.appendChild(makeBadge(s)));

    node.querySelector("h2").textContent = entry.title;
    node.querySelector(".id").textContent = entry.id;
    node.querySelector(".description").textContent = entry.description || "";

    const metrics = node.querySelector(".metrics");
    Object.entries(entry.summaryMetrics || {}).forEach(([key, value]) => {
      const dt = document.createElement("dt");
      const dd = document.createElement("dd");
      dt.textContent = metricLabels[key] || key;
      dd.textContent = formatMetric(key, value);
      metrics.append(dt, dd);
    });

    node.querySelector(".detail-grid").appendChild(buildDetail(entry));

    const links = node.querySelector(".links");
    if (artifact(entry, "video")) links.appendChild(makeLink("video", assetRoot + "/" + encodeURIComponent(entry.id) + "/media.mp4"));
    links.appendChild(makeLink("validation", assetRoot + "/" + encodeURIComponent(entry.id) + "/validation.json"));
    if (entry.links?.source) links.appendChild(makeLink("source", entry.links.source));
    if (entry.links?.result) links.appendChild(makeLink("result", entry.links.result));
    if (entry.links?.actions) links.appendChild(makeLink("Actions #" + entry.run.runNumber, entry.links.actions));
    if (entry.links?.commit) links.appendChild(makeLink("commit", entry.links.commit));

    return node;
  }

  function matches(entry) {
    const q = searchInput.value.trim().toLowerCase();
    if (categoryFilter.value && entry.category !== categoryFilter.value) return false;
    if (systemFilter.value && !(entry.systems || []).includes(systemFilter.value)) return false;
    if (tagFilter.value && !(entry.tags || []).includes(tagFilter.value)) return false;
    if (!q) return true;
    const haystack = [
      entry.id, entry.title, entry.description, entry.category, entry.series,
      ...(entry.systems || []), ...(entry.tags || [])
    ].join(" ").toLowerCase();
    return haystack.includes(q);
  }

  function sortEntries(entries) {
    const mode = sortOrder.value;
    return entries.sort((a, b) => {
      if (mode === "oldest") return (a.firstPublishEpoch || 0) - (b.firstPublishEpoch || 0) || a.id.localeCompare(b.id);
      if (mode === "title") return a.title.localeCompare(b.title);
      if (mode === "category") return a.category.localeCompare(b.category) || a.title.localeCompare(b.title);
      return (b.firstPublishEpoch || 0) - (a.firstPublishEpoch || 0) || b.id.localeCompare(a.id);
    });
  }

  function render() {
    if (!payload) return;
    const visible = sortEntries(payload.experiments.filter(matches));
    cardsEl.replaceChildren(...visible.map(buildCard));
    emptyState.hidden = visible.length !== 0;
    document.getElementById("visibleCount").textContent = visible.length.toLocaleString();

    const parts = [];
    if (searchInput.value.trim()) parts.push('search: "' + searchInput.value.trim() + '"');
    if (categoryFilter.value) parts.push("category: " + categoryFilter.value);
    if (systemFilter.value) parts.push("system: " + systemFilter.value);
    if (tagFilter.value) parts.push("tag: " + tagFilter.value);
    activeFilter.hidden = parts.length === 0;
    activeFilter.textContent = parts.length ? parts.join(" · ") : "";
  }

  async function boot() {
    try {
      const response = await fetch(dataPath, { cache: "no-store" });
      if (!response.ok) throw new Error("HTTP " + response.status);
      payload = await response.json();

      document.getElementById("experimentCount").textContent = payload.counts.experiments.toLocaleString();
      document.getElementById("categoryCount").textContent = payload.counts.categories.toLocaleString();
      document.getElementById("systemCount").textContent = payload.counts.systems.toLocaleString();

      (payload.facets.categories || []).forEach(v => option(categoryFilter, v));
      (payload.facets.systems || []).forEach(v => option(systemFilter, v));
      (payload.facets.tags || []).forEach(v => option(tagFilter, v));

      [searchInput, categoryFilter, systemFilter, tagFilter, sortOrder].forEach(el => {
        el.addEventListener(el === searchInput ? "input" : "change", render);
      });
      render();
    } catch (error) {
      cardsEl.innerHTML = '<p class="error">Failed to load experiment index: ' + String(error) + '</p>';
    }
  }

  boot();
})();

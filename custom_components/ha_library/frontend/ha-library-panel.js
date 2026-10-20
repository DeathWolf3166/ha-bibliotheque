/* Bibliothèque HA — sidebar panel (vanilla custom element, no build step). */
const CTX = { particulier: "Particulier", hotel: "Hôtel", logistique: "Site logistique", bureau: "Bureau" };
const KIND = { automation: "auto", script: "script", scene: "scène", helper: "helper", template: "template", yaml: "yaml", file: "fichier" };
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const fmtDate = (s) => { try { return new Date(s).toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" }); } catch (e) { return s || ""; } };

const CSS = `
:host{display:block;height:100%;background:var(--primary-background-color);color:var(--primary-text-color);font-family:var(--paper-font-body1_-_font-family,Roboto,system-ui,sans-serif);
  --lib-accent:var(--primary-color,#03a9f4);--lib-card:var(--card-background-color,#fff);--lib-line:var(--divider-color,#e0e0e0);--lib-muted:var(--secondary-text-color,#727272);
  --lib-sunk:var(--secondary-background-color,#f2f2f2);--lib-warn:var(--warning-color,#ffa600);--lib-bad:var(--error-color,#db4437);--lib-ok:var(--success-color,#43a047);
  --lib-radius:var(--ha-card-border-radius,12px);--lib-mono:var(--code-font-family,"Roboto Mono",ui-monospace,Consolas,monospace)}
*{box-sizing:border-box}
.top{position:sticky;top:0;z-index:4;display:flex;align-items:center;gap:8px;height:var(--header-height,56px);padding:0 12px;background:var(--app-header-background-color,var(--primary-color));color:var(--app-header-text-color,#fff);border-bottom:var(--app-header-border-bottom,none)}
.top h1{font-size:20px;font-weight:400;margin:0 12px 0 4px;white-space:nowrap}
.menu{background:none;border:0;color:inherit;width:40px;height:40px;border-radius:50%;cursor:pointer;display:flex;align-items:center;justify-content:center}
.tabs{display:flex;gap:2px;overflow-x:auto;flex:1;min-width:0}
.tabs button{background:none;border:0;color:inherit;opacity:.75;padding:0 14px;height:var(--header-height,56px);cursor:pointer;font:inherit;font-size:14px;border-bottom:2px solid transparent;white-space:nowrap}
.tabs button[aria-selected=true]{opacity:1;border-bottom-color:currentColor;font-weight:500}
.wrap{max-width:1400px;margin:0 auto;padding:16px}
.bar{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-bottom:12px}
.bar .grow{flex:1 1 220px;min-width:0}
input[type=search],input[type=text],input[type=password],select,textarea{font:inherit;color:inherit;background:var(--lib-card);border:1px solid var(--lib-line);border-radius:8px;padding:8px 10px;min-width:0;max-width:100%}
textarea{width:100%;font-family:var(--lib-mono);font-size:12.5px;min-height:280px}
.seg{display:inline-flex;flex-wrap:wrap;border:1px solid var(--lib-line);border-radius:8px;overflow:hidden;background:var(--lib-card)}
.seg button{background:none;border:0;border-right:1px solid var(--lib-line);padding:7px 11px;font:inherit;font-size:13px;color:inherit;cursor:pointer}
.seg button:last-child{border-right:0}
.seg button[aria-pressed=true]{background:var(--lib-accent);color:var(--text-primary-color,#fff)}
.btn{font:inherit;font-size:14px;font-weight:500;border:1px solid var(--lib-line);background:var(--lib-card);color:var(--primary-text-color);padding:7px 14px;border-radius:8px;cursor:pointer;display:inline-flex;align-items:center;gap:6px;white-space:nowrap}
.btn:hover{border-color:var(--lib-muted)}
.btn.primary{background:var(--lib-accent);border-color:var(--lib-accent);color:var(--text-primary-color,#fff)}
.btn.danger{color:var(--lib-bad);border-color:var(--lib-bad)}
.btn[disabled]{opacity:.5;cursor:default}
.btn.small{font-size:12.5px;padding:4px 10px}
.grid{display:grid;grid-template-columns:minmax(0,5fr) minmax(0,7fr);gap:16px;align-items:start}
@media (max-width:900px){.grid{grid-template-columns:minmax(0,1fr)}}
.list{display:flex;flex-direction:column;gap:8px;min-width:0}
.card{background:var(--lib-card);border:1px solid var(--lib-line);border-radius:var(--lib-radius);padding:12px 14px;min-width:0}
.pkg{cursor:pointer;display:grid;grid-template-columns:auto minmax(0,1fr) auto;gap:4px 10px;align-items:start}
.pkg:hover{border-color:var(--lib-muted)}
.pkg[aria-current=true]{border-color:var(--lib-accent);box-shadow:inset 3px 0 0 var(--lib-accent)}
.pkg h3{margin:0;font-size:15px;font-weight:500;line-height:1.3}
.pkg .meta{grid-column:2/4;display:flex;flex-wrap:wrap;gap:4px 6px;align-items:center}
.pick{width:18px;height:18px;margin:1px 0 0;accent-color:var(--lib-accent);cursor:pointer}
.ref{font-family:var(--lib-mono);font-size:11px;color:var(--lib-muted);overflow-wrap:anywhere}
.chip{display:inline-flex;align-items:center;font-size:11.5px;line-height:1.6;padding:0 7px;border-radius:999px;border:1px solid var(--lib-line);white-space:nowrap}
.chip.mono{font-family:var(--lib-mono);font-size:11px;background:var(--lib-sunk);border-color:transparent}
.chip.ctx{border-color:var(--lib-accent);color:var(--lib-accent)}
.chip.ok{background:color-mix(in srgb,var(--lib-ok) 16%,transparent);color:var(--lib-ok);border-color:transparent}
.chip.warn{background:color-mix(in srgb,var(--lib-warn) 18%,transparent);color:color-mix(in srgb,var(--lib-warn) 80%,var(--primary-text-color));border-color:transparent}
.chip.bad{background:color-mix(in srgb,var(--lib-bad) 14%,transparent);color:var(--lib-bad);border-color:transparent}
.counts{font-size:12px;color:var(--lib-muted)}
.detail{position:sticky;top:calc(var(--header-height,56px) + 12px);max-height:calc(100vh - var(--header-height,56px) - 28px);overflow:auto;padding:0}
@media (max-width:900px){.detail{position:static;max-height:none}}
.dh{padding:16px 18px 12px;border-bottom:1px solid var(--lib-line);display:flex;flex-direction:column;gap:8px}
.dh h2{margin:0;font-size:20px;font-weight:500}
.dh p{margin:0;color:var(--lib-muted);max-width:70ch}
.sub{display:flex;gap:2px;padding:0 12px;border-bottom:1px solid var(--lib-line);overflow-x:auto}
.sub button{background:none;border:0;padding:10px;font:inherit;font-size:13.5px;color:var(--lib-muted);border-bottom:2px solid transparent;cursor:pointer;white-space:nowrap}
.sub button[aria-selected=true]{color:var(--primary-text-color);border-bottom-color:var(--lib-accent);font-weight:500}
.db{padding:14px 18px 18px;display:flex;flex-direction:column;gap:14px;min-width:0}
.sec{display:flex;flex-direction:column;gap:6px;min-width:0}
.label{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--lib-muted);font-weight:500}
.row{display:flex;flex-wrap:wrap;gap:6px;align-items:center}
pre{margin:0;background:var(--lib-sunk);border-radius:8px;padding:12px;font:12px/1.55 var(--lib-mono);overflow:auto;max-height:480px;white-space:pre}
pre .k{color:var(--lib-accent)} pre .c{color:var(--lib-muted);font-style:italic} pre .s{color:var(--lib-bad)}
details.it{border:1px solid var(--lib-line);border-radius:10px;overflow:hidden}
details.it summary{padding:8px 12px;cursor:pointer;display:flex;flex-wrap:wrap;gap:6px 10px;align-items:center;list-style:none}
details.it summary::-webkit-details-marker{display:none}
details.it .t{flex:1 1 200px;min-width:0;font-weight:500}
details.it .ib{padding:0 12px 12px;display:flex;flex-direction:column;gap:8px}
.kind{font:500 10.5px var(--lib-mono);text-transform:uppercase;padding:1px 6px;border-radius:4px;background:var(--lib-sunk);color:var(--lib-muted)}
.note{background:var(--lib-sunk);border-radius:10px;padding:10px 12px;font-size:13.5px}
.note.warn{background:color-mix(in srgb,var(--lib-warn) 14%,var(--lib-card))}
.note.bad{background:color-mix(in srgb,var(--lib-bad) 12%,var(--lib-card))}
.note.ok{background:color-mix(in srgb,var(--lib-ok) 12%,var(--lib-card))}
.empty{padding:40px 16px;text-align:center;color:var(--lib-muted)}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{text-align:left;padding:6px;border-bottom:1px solid var(--lib-line);vertical-align:top}
th{font-size:11px;text-transform:uppercase;letter-spacing:.07em;color:var(--lib-muted);font-weight:500}
td.m{font-family:var(--lib-mono);font-size:12px;word-break:break-all}
td input,td select{width:100%;font-family:var(--lib-mono);font-size:12px;padding:5px 8px}
.tw{overflow-x:auto}
.sug{display:flex;flex-wrap:wrap;gap:4px;margin-top:4px}
.sug button{font:11px var(--lib-mono);border:1px dashed var(--lib-line);background:none;color:var(--lib-accent);border-radius:999px;padding:1px 8px;cursor:pointer}
.stats{display:flex;flex-wrap:wrap;gap:6px 22px}
.stats div{display:flex;flex-direction:column}
.stats b{font-size:22px;font-weight:500;line-height:1.1;font-variant-numeric:tabular-nums}
.stats small{font-size:11px;color:var(--lib-muted);text-transform:uppercase;letter-spacing:.06em}
.tray{position:sticky;bottom:0;z-index:3;margin-top:16px;background:var(--lib-card);border:1px solid var(--lib-line);border-radius:var(--lib-radius);padding:10px 14px;display:flex;flex-wrap:wrap;gap:8px 14px;align-items:center;justify-content:space-between;box-shadow:0 -2px 12px rgba(0,0,0,.08)}
.modal{position:fixed;inset:0;z-index:10;background:rgba(0,0,0,.45);display:flex;align-items:flex-start;justify-content:center;padding:4vh 12px;overflow:auto}
.modal .box{background:var(--lib-card);border-radius:var(--lib-radius);width:min(920px,100%);display:flex;flex-direction:column;box-shadow:0 10px 40px rgba(0,0,0,.3)}
.modal .mh{padding:16px 18px;border-bottom:1px solid var(--lib-line);display:flex;justify-content:space-between;gap:12px;align-items:center}
.modal .mh h2{margin:0;font-size:19px;font-weight:500}
.modal .mb{padding:14px 18px;display:flex;flex-direction:column;gap:14px}
.modal .mf{padding:12px 18px;border-top:1px solid var(--lib-line);display:flex;flex-wrap:wrap;gap:8px;justify-content:flex-end;align-items:center}
.toast{position:fixed;left:50%;bottom:24px;transform:translateX(-50%);z-index:20;background:var(--primary-text-color);color:var(--primary-background-color);padding:10px 18px;border-radius:8px;font-size:14px;max-width:min(560px,90vw);white-space:pre-line}
.spin{display:inline-block;width:14px;height:14px;border:2px solid currentColor;border-right-color:transparent;border-radius:50%;animation:sp .8s linear infinite}
@keyframes sp{to{transform:rotate(360deg)}}
@media (prefers-reduced-motion:reduce){.spin{animation:none}}
.form{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:10px}
.form label{display:flex;flex-direction:column;gap:4px;font-size:12.5px;color:var(--lib-muted)}
.form label input{color:var(--primary-text-color)}
`;

class HaLibraryPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this.s = {
      tab: "library", source: "local", lib: null, sel: null, sub: "apercu", pkgCache: {}, q: "", ctx: "", integ: "", libView: "packages",
      cart: new Set(), scan: null, scanSel: null, scanSub: "apercu", settings: null, busy: null, modal: null, confirm: null,
    };
    this._booted = false;
  }

  set hass(h) { this._hass = h; if (!this._booted) { this._booted = true; this.boot(); } }
  get hass() { return this._hass; }
  set narrow(n) { this._narrow = n; if (this._booted) this.renderTop(); }
  set panel(p) { this._panel = p; }

  ws(type, data = {}) { return this._hass.callWS({ type: `ha_library/${type}`, ...data }); }
  toast(msg, ms = 2600) {
    const t = this.shadowRoot.querySelector(".toast");
    t.textContent = msg; t.hidden = false; clearTimeout(this._tt); this._tt = setTimeout(() => (t.hidden = true), ms);
  }
  err(e) { this.toast(e?.message || String(e), 7000); }

  async boot() {
    this.shadowRoot.innerHTML = `<style>${CSS}</style><div class="top"></div><div class="wrap" id="main"></div><div id="modal"></div><div class="toast" hidden></div>`;
    this.shadowRoot.addEventListener("click", (e) => this.onClick(e));
    this.shadowRoot.addEventListener("input", (e) => this.onInput(e));
    this.shadowRoot.addEventListener("change", (e) => this.onChange(e));
    this.shadowRoot.addEventListener("toggle", (e) => this.onToggle(e), true);
    this.renderTop();
    try {
      this.s.settings = await this.ws("settings/get");
      this.s.scan = await this.ws("scan/result");
    } catch (e) { this.err(e); }
    await this.loadLibrary();
  }

  async loadLibrary() {
    this.s.busy = "lib"; this.render();
    try { this.s.lib = await this.ws("library", { source_id: this.s.source }); this.s.pkgCache = {}; }
    catch (e) { this.s.lib = { packages: [], views: [] }; this.err(e); }
    this.s.busy = null; this.render();
  }

  // ------------------------------------------------------------ render
  renderTop() {
    const top = this.shadowRoot.querySelector(".top"); if (!top) return;
    const tabs = [["library", "Bibliothèque"], ["instance", "Cette instance"], ["installed", "Installés"], ["settings", "Réglages"]];
    top.innerHTML = `${this._narrow ? `<button class="menu" data-act="menu" aria-label="Menu"><svg width="24" height="24" viewBox="0 0 24 24"><path fill="currentColor" d="M3 6h18v2H3zm0 5h18v2H3zm0 5h18v2H3z"/></svg></button>` : ""}
      ${this._narrow ? "" : "<h1>Bibliothèque</h1>"}<nav class="tabs" role="tablist">${tabs.map(([k, l]) => `<button role="tab" data-tab="${k}" aria-selected="${this.s.tab === k}">${l}</button>`).join("")}</nav>`;
  }

  render() {
    this.renderTop();
    const m = this.shadowRoot.getElementById("main");
    m.innerHTML = { library: () => this.vLibrary(), instance: () => this.vInstance(), installed: () => this.vInstalled(), settings: () => this.vSettings() }[this.s.tab]();
    this.renderModal();
  }

  ctxChips(c) { return (c || []).map((x) => `<span class="chip ctx">${CTX[x] || esc(x)}</span>`).join(""); }
  hl(txt) {
    let h = esc(txt);
    h = h.replace(/^(\s*#.*)$/gm, '<span class="c">$1</span>');
    h = h.replace(/^(\s*-?\s*)([A-Za-z_][\w]*)(:)(?=\s|$)/gm, '$1<span class="k">$2</span>$3');
    h = h.replace(/!secret [\w]+|&lt;SECRET:[\w,]+&gt;/g, (x) => `<span class="s">${x}</span>`);
    return h;
  }
  counts(c) {
    c = c || {};
    return [["automation", "auto"], ["script", "script"], ["scene", "scène"], ["helper", "helper"], ["template", "template"], ["yaml", "yaml"], ["file", "fichier"]]
      .filter(([k]) => c[k]).map(([k, l]) => `${c[k]} ${l}${c[k] > 1 && !["auto", "yaml"].includes(l) ? "s" : ""}`).join(" · ");
  }

  sources() { return this.s.settings?.sources || [{ id: "local", type: "local", name: "Bibliothèque locale" }]; }

  // ------------------------------------------------------------ library tab
  filtered() {
    const q = this.s.q.toLowerCase();
    return (this.s.lib?.packages || []).filter((p) => {
      if (this.s.ctx && !(p.contexts || []).includes(this.s.ctx)) return false;
      if (this.s.integ && !(p.integrations || []).includes(this.s.integ)) return false;
      if (q) {
        const hay = [p.title, p.description, p.id, ...(p.integrations || []), ...(p.provides || []), ...(p.items_summary || []).map((i) => i.name)].join(" ").toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }

  vLibrary() {
    const src = this.sources().find((x) => x.id === this.s.source) || this.sources()[0];
    const lib = this.s.lib;
    const integs = [...new Set((lib?.packages || []).flatMap((p) => p.integrations || []))].sort();
    const head = `<div class="bar">
      <select data-k="source" aria-label="Source">${this.sources().map((x) => `<option value="${esc(x.id)}" ${x.id === this.s.source ? "selected" : ""}>${esc(x.type === "local" ? "Bibliothèque locale" : "GitHub · " + x.repo)}</option>`).join("")}</select>
      ${src?.type === "github" ? `<button class="btn" data-act="refresh">${this.s.busy === "refresh" ? '<span class="spin"></span>' : ""}Télécharger la dernière version</button><span class="counts">${src.fetched_at ? "Mis à jour " + fmtDate(src.fetched_at) : "Jamais téléchargé"}</span>` : ""}
      <span class="grow"></span>
      <div class="seg" role="group" aria-label="Affichage"><button data-lv="packages" aria-pressed="${this.s.libView === "packages"}">Packages</button><button data-lv="views" aria-pressed="${this.s.libView === "views"}">Vues de dashboard</button></div>
    </div>`;
    if (this.s.busy === "lib") return head + `<div class="empty"><span class="spin"></span></div>`;
    if (!lib?.packages?.length && !lib?.views?.length) {
      return head + `<div class="card empty">${src?.type === "github" ? "Cette bibliothèque est vide ou pas encore téléchargée. Utilisez « Télécharger la dernière version »." : "La bibliothèque locale est vide. Allez dans « Cette instance », lancez un scan puis exportez les packages."}</div>`;
    }
    if (this.s.libView === "views") return head + this.vViews();
    const list = this.filtered();
    if (!this.s.sel || !list.find((p) => p.id === this.s.sel)) this.s.sel = list[0]?.id || null;
    const filters = `<div class="bar"><input type="search" class="grow" data-k="q" placeholder="Rechercher : nom, entité, intégration…" value="${esc(this.s.q)}">
      <div class="seg" role="group" aria-label="Contexte">${[["", "Tous"], ...Object.entries(CTX)].map(([k, l]) => `<button data-ctx="${k}" aria-pressed="${this.s.ctx === k}">${l}</button>`).join("")}</div>
      <select data-k="integ"><option value="">Toutes les intégrations</option>${integs.map((i) => `<option ${i === this.s.integ ? "selected" : ""}>${esc(i)}</option>`).join("")}</select></div>`;
    const cards = list.map((p) => `<div class="card pkg" data-pkg="${esc(p.id)}" aria-current="${p.id === this.s.sel}" tabindex="0">
        <input type="checkbox" class="pick" data-pick="${esc(p.id)}" ${this.s.cart.has(p.id) ? "checked" : ""} aria-label="Sélectionner ${esc(p.title)}">
        <h3>${esc(p.title)}</h3><span class="ref">${esc(p.source?.slug || "")}</span>
        <div class="meta">${this.ctxChips(p.contexts)}<span class="counts">${this.counts(p.counts)}</span></div>
        <div class="meta">${(p.integrations || []).slice(0, 5).map((i) => `<span class="chip mono">${esc(i)}</span>`).join("")}${(p.integrations || []).length > 5 ? `<span class="counts">+${p.integrations.length - 5}</span>` : ""}
          ${p.installed ? (p.installed.update ? '<span class="chip warn">mise à jour disponible</span>' : '<span class="chip ok">installé</span>') : ""}
          ${(p.requires || []).length ? `<span class="chip">${p.requires.length} dépendance${p.requires.length > 1 ? "s" : ""}</span>` : ""}</div>
      </div>`).join("") || `<div class="card empty">Aucun package ne correspond.</div>`;
    const tray = this.s.cart.size ? `<div class="tray"><span><b>${this.s.cart.size}</b> package${this.s.cart.size > 1 ? "s" : ""} sélectionné${this.s.cart.size > 1 ? "s" : ""} (les dépendances sont ajoutées automatiquement)</span>
      <span class="row"><button class="btn" data-act="clearcart">Vider</button><button class="btn primary" data-act="install-cart">Installer la sélection…</button></span></div>` : "";
    return head + filters + `<div class="grid"><div class="list">${cards}</div><section class="card detail">${this.s.sel ? this.vPkgDetail() : ""}</section></div>` + tray;
  }

  vPkgDetail() {
    const meta = this.s.lib.packages.find((p) => p.id === this.s.sel);
    const full = this.s.pkgCache[this.s.sel];
    if (!full) { this.fetchPkg(this.s.sel); }
    const p = full || meta;
    const subs = [["apercu", "Aperçu"], ["yaml", "package.yaml"], ["elements", `Éléments (${(meta.items_summary || meta.items || []).length})`]];
    let body = "";
    if (this.s.sub === "apercu") {
      const reqTitles = (p.requires || []).map((r) => this.s.lib.packages.find((x) => x.id === r)?.title || r);
      body = `
        <div class="sec"><span class="label">Intégrations nécessaires</span><div class="row">${(p.integrations || []).map((i) => `<span class="chip mono">${esc(i)}</span>`).join("") || '<span class="counts">Aucune en dehors du cœur de HA</span>'}</div></div>
        ${reqTitles.length ? `<div class="sec"><span class="label">Packages requis</span><div class="row">${reqTitles.map((t) => `<span class="chip">${esc(t)}</span>`).join("")}</div></div>` : ""}
        <div class="sec"><span class="label">Crée sur l’instance (${(p.provides || []).length})</span><div class="row">${(p.provides || []).slice(0, 40).map((e) => `<span class="chip mono">${esc(e)}</span>`).join("")}${(p.provides || []).length > 40 ? `<span class="counts">+${p.provides.length - 40}</span>` : ""}</div></div>
        <div class="sec"><span class="label">Entités à fournir (${(p.entities_to_provide || []).length})</span><div class="row">${(p.entities_to_provide || []).slice(0, 40).map((e) => `<span class="chip mono">${esc(e)}</span>`).join("") || '<span class="counts">Aucune</span>'}${(p.entities_to_provide || []).length > 40 ? `<span class="counts">+${p.entities_to_provide.length - 40}</span>` : ""}</div></div>
        ${(p.notify_targets || []).length ? `<div class="sec"><span class="label">Notifications à rediriger</span><div class="row">${p.notify_targets.map((e) => `<span class="chip mono">${esc(e)}</span>`).join("")}</div></div>` : ""}
        ${(p.secrets || []).length ? `<div class="sec"><span class="label">Secrets demandés à l’installation</span><div class="row">${p.secrets.map((e) => `<span class="chip mono">${esc(e)}</span>`).join("")}</div></div>` : ""}
        ${(p.missing_on_source || []).length ? `<div class="note warn">Ces entités n’existaient déjà plus sur l’instance d’origine : ${p.missing_on_source.map(esc).join(", ")}</div>` : ""}
        ${(p.devices || []).length ? `<div class="sec"><span class="label">Appareils précis utilisés (${p.devices.length})</span><div class="row">${p.devices.map((d) => `<span class="chip">${esc(d.name)}${d.model ? " · " + esc(d.model) : ""}</span>`).join("")}</div><div class="counts">À l’installation, vous choisissez l’appareil équivalent ; des appareils du même modèle sont proposés.</div></div>` : ((p.device_ids || []).length ? `<div class="note">${p.device_ids.length} référence(s) à un appareil précis (device_id) : la correspondance est proposée à l’installation.</div>` : "")}
        ${p.source ? `<div class="counts">Exporté depuis « ${esc(p.source.name)} » le ${fmtDate(p.source.exported_at)} · version ${esc(p.version)}</div>` : ""}`;
    } else if (this.s.sub === "yaml") {
      body = full ? `<div class="row" style="justify-content:flex-end"><button class="btn small" data-copy="pkg">Copier</button></div><pre>${this.hl(full.yaml)}</pre>` : `<div class="empty"><span class="spin"></span></div>`;
    } else {
      body = full ? (full.items_detail || []).map((i) => this.itemBlock(i)).join("") : `<div class="empty"><span class="spin"></span></div>`;
    }
    return `<div class="dh"><div class="row">${this.ctxChips(meta.contexts)}<span class="ref">${esc(meta.id)}</span></div><h2>${esc(meta.title)}</h2>${meta.description ? `<p>${esc(meta.description)}</p>` : ""}
      <div class="row"><button class="btn primary" data-install="${esc(meta.id)}">${meta.installed ? (meta.installed.update ? "Mettre à jour…" : "Réinstaller…") : "Installer…"}</button>
      ${this.s.source === "local" ? `<button class="btn" data-act="lib-remove" data-id="${esc(meta.id)}">Retirer de la bibliothèque</button>` : ""}</div></div>
      <div class="sub" role="tablist">${subs.map(([k, l]) => `<button role="tab" data-sub="${k}" aria-selected="${this.s.sub === k}">${l}</button>`).join("")}</div><div class="db">${body}</div>`;
  }

  itemBlock(i, extra = "") {
    const yaml = i.file ? i.file.content : i.yaml;
    return `<details class="it"><summary><span class="kind">${KIND[i.kind] || esc(i.kind)}</span><span class="t">${esc(i.name)}</span>${i.enabled === false ? '<span class="chip warn">désactivée</span>' : ""}${(i.missing || []).length ? `<span class="chip bad">${i.missing.length} réf. cassée${i.missing.length > 1 ? "s" : ""}</span>` : ""}<span class="ref">${esc(i.file ? i.file.path : (i.provides || [])[0] || i.key)}</span></summary>
      <div class="ib">${i.description ? `<div class="counts">${esc(i.description)}</div>` : ""}
      ${(i.uses || []).length ? `<div class="counts"><span class="label">Utilise</span> ${i.uses.map(esc).join(", ")}</div>` : ""}
      ${(i.used_by || []).length ? `<div class="counts"><span class="label">Utilisé par</span> ${i.used_by.map(esc).join(", ")}</div>` : ""}
      ${["automation", "script"].includes(i.kind) && !/use_blueprint/.test(yaml || "") ? `<div class="row" style="justify-content:flex-end"><button class="btn small" data-bp="${esc(i.uid)}">Créer un blueprint</button></div>` : ""}
      ${extra}<pre data-lazy="1">${this.hl(yaml || "")}</pre></div></details>`;
  }

  async fetchPkg(id) {
    if (this._fetching === id) return;
    this._fetching = id;
    try { this.s.pkgCache[id] = await this.ws("package", { source_id: this.s.source, package_id: id }); }
    catch (e) { this.err(e); }
    this._fetching = null;
    if (this.s.tab === "library" && this.s.sel === id) this.render();
  }

  vViews() {
    const views = this.s.lib?.views || [];
    if (!views.length) return `<div class="card empty">Aucune vue de dashboard dans cette bibliothèque.</div>`;
    const res = new Set((this._resources || []).map((r) => r.url));
    const dashes = (this._dashes || []).filter((x) => x.mode === "storage");
    const dashOpts = dashes.map((x) => `<option value="${esc(x.url_path)}">${esc(x.title)}</option>`).join("");
    return `<div class="note" style="margin-bottom:10px">« Ajouter » place la vue à la fin du dashboard choisi, avec vos correspondances d’entités ; une sauvegarde du dashboard est faite avant. Les cartes <code>custom:</code> manquantes s’installent via HACS.</div>
      <div class="list">${views.map((v) => `<details class="it" data-view="${esc(v.id)}"><summary><span class="kind">vue</span><span class="t">${esc(v.title)}</span><span class="counts">${esc(v.dashboard)} · ${v.entities} entités · ${(v.size / 1024).toFixed(1)} Ko</span></summary>
        <div class="ib"><div class="row">${(v.custom_cards || []).map((c) => `<span class="chip mono">custom:${esc(c)}</span>`).join("") || '<span class="counts">Cartes natives uniquement</span>'}</div>
        <div class="row" style="justify-content:flex-end">${dashOpts ? `<select data-dash-for="${esc(v.id)}" aria-label="Dashboard cible">${dashOpts}</select><button class="btn small primary" data-addview="${esc(v.id)}">Ajouter à ce dashboard</button>` : ""}<button class="btn small" data-copy-view="${esc(v.id)}">Copier le YAML</button></div><pre data-view-yaml="${esc(v.id)}">Ouverture…</pre></div></details>`).join("")}</div>`;
  }

  // ------------------------------------------------------------ instance tab
  vInstance() {
    const sc = this.s.scan;
    const busy = this.s.busy === "scan";
    const head = `<div class="bar"><button class="btn primary" data-act="scan" ${busy ? "disabled" : ""}>${busy ? '<span class="spin"></span> Scan en cours…' : sc ? "Relancer le scan" : "Scanner cette instance"}</button>
      ${sc ? `<span class="counts">Scan de « ${esc(sc.instance?.name)} » du ${fmtDate(sc.instance?.exported_at)}</span>` : ""}<span class="grow"></span>
      ${sc ? `<button class="btn" data-act="export">${this.s.busy === "export" ? '<span class="spin"></span>' : ""}Exporter vers la bibliothèque locale</button>
      ${this.s.settings?.publish_to ? `<button class="btn" data-act="publish">${this.s.busy === "publish" ? '<span class="spin"></span>' : ""}Publier sur GitHub</button>` : ""}` : ""}</div>`;
    if (!sc) {
      return head + `<div class="card"><p style="margin:0 0 8px">Le scan lit tout ce qui est réutilisable sur cette instance : automatisations et scripts (interface et YAML), scènes, helpers, capteurs template, plateformes YAML, pyscript, python_scripts, blueprints et vues de dashboard.</p>
        <p style="margin:0;color:var(--lib-muted)">Il regroupe le tout en packages avec leurs dépendances. Rien n’est modifié sur l’instance ; les secrets sont remplacés par <code>!secret</code>.</p></div>`;
    }
    const pk = sc.packages || [];
    const stat = (n, l) => `<div><b>${n}</b><small>${l}</small></div>`;
    const kinds = Object.values(sc.items || {}).reduce((a, i) => ((a[i.kind] = (a[i.kind] || 0) + 1), a), {});
    const summary = `<div class="card" style="margin-bottom:12px"><div class="stats">${stat(pk.length, "packages")}${stat(kinds.automation || 0, "automatisations")}${stat(kinds.script || 0, "scripts")}${stat(kinds.scene || 0, "scènes")}${stat(kinds.helper || 0, "helpers")}${stat(kinds.template || 0, "templates")}${stat((kinds.yaml || 0) + (kinds.file || 0), "yaml & fichiers")}${stat((sc.views || []).length, "vues")}</div>
      <div class="row" style="margin-top:10px">${sc.redactions ? `<span class="chip warn">${sc.redactions} valeur${sc.redactions > 1 ? "s" : ""} sensible${sc.redactions > 1 ? "s" : ""} remplacée${sc.redactions > 1 ? "s" : ""} par !secret</span>` : '<span class="chip ok">Aucune valeur sensible détectée</span>'}
      ${(sc.orphans || []).length ? `<span class="chip bad" title="${esc(sc.orphans.join(", "))}">${sc.orphans.length} automatisations/scripts fantômes dans le registre</span><button class="btn small" data-act="ghosts">Nettoyer…</button>` : ""}</div></div>`;
    if (!this.s.scanSel || !pk.find((p) => p.id === this.s.scanSel)) this.s.scanSel = pk[0]?.id;
    const ov = sc.overrides?.packages || {};
    const cards = pk.map((p) => `<div class="card pkg" data-spkg="${esc(p.id)}" aria-current="${p.id === this.s.scanSel}" tabindex="0">
      <input type="checkbox" class="pick" data-incl="${esc(p.id)}" ${p.exclude ? "" : "checked"} aria-label="Exporter ${esc(p.title)}">
      <h3>${esc(p.title)}</h3><span class="ref">${esc(p.id)}</span>
      <div class="meta">${this.ctxChips(p.contexts)}<span class="counts">${this.counts(p.counts)}</span></div>
      <div class="meta">${(p.requires || []).length ? `<span class="chip">requiert ${p.requires.map(esc).join(", ")}</span>` : ""}${(p.missing_on_source || []).length ? `<span class="chip warn">${p.missing_on_source.length} réf. cassée${p.missing_on_source.length > 1 ? "s" : ""}</span>` : ""}${(p.secrets || []).length ? `<span class="chip mono">${p.secrets.length} secret${p.secrets.length > 1 ? "s" : ""}</span>` : ""}</div></div>`).join("");
    return head + summary + `<div class="grid"><div class="list">${cards}</div><section class="card detail">${this.s.scanSel ? this.vScanDetail(pk.find((p) => p.id === this.s.scanSel)) : ""}</section></div>`;
  }

  vScanDetail(p) {
    const items = this.s.scan.items || {};
    const pk = this.s.scan.packages || [];
    const subs = [["apercu", "Réglages du package"], ["yaml", "package.yaml"], ["elements", `Éléments (${p.items.length})`]];
    let body = "";
    if (this.s.scanSub === "apercu") {
      body = `<div class="form"><label>Titre<input type="text" id="ov-title" value="${esc(p.title)}"></label><label>Description<input type="text" id="ov-desc" value="${esc(p.description || "")}"></label></div>
        <div class="sec"><span class="label">Contextes d’usage</span><div class="row">${Object.entries(CTX).map(([k, l]) => `<label class="chip" style="gap:6px;padding:3px 10px;cursor:pointer"><input type="checkbox" class="ov-ctx" value="${k}" ${(p.contexts || []).includes(k) ? "checked" : ""}> ${l}</label>`).join("")}</div></div>
        <div class="row"><button class="btn primary small" data-act="save-ov" data-id="${esc(p.id)}">Enregistrer</button><span class="counts">Conservé aux prochains scans.</span></div>
        <div class="sec"><span class="label">Intégrations</span><div class="row">${(p.integrations || []).map((i) => `<span class="chip mono">${esc(i)}</span>`).join("") || '<span class="counts">Aucune</span>'}</div></div>
        <div class="sec"><span class="label">Entités à fournir sur une autre instance (${p.entities_to_provide.length})</span><div class="row">${p.entities_to_provide.slice(0, 50).map((e) => `<span class="chip mono">${esc(e)}</span>`).join("") || '<span class="counts">Aucune</span>'}</div></div>
        ${(p.missing_on_source || []).length ? `<div class="note warn"><b>Références cassées</b> : ces entités sont utilisées mais n’existent pas sur cette instance. ${p.missing_on_source.map(esc).join(", ")}</div>` : ""}`;
    } else if (this.s.scanSub === "yaml") {
      body = `<pre>${this.hl(p.yaml)}</pre>`;
    } else {
      const opts = pk.map((x) => `<option value="${esc(x.id)}">${esc(x.title)}</option>`).join("");
      body = p.items.map((u) => {
        const i = items[u]; if (!i) return "";
        const mover = `<div class="row"><span class="label">Déplacer vers</span><select data-move="${esc(u)}"><option value="">— garder ici —</option>${opts}<option value="__new__">Nouveau package…</option></select>${(this.s.scan.overrides?.items || {})[u] ? `<button class="btn small" data-unmove="${esc(u)}">Annuler le déplacement</button>` : ""}</div>`;
        return this.itemBlock(i, mover);
      }).join("");
    }
    return `<div class="dh"><div class="row">${this.ctxChips(p.contexts)}<span class="ref">${esc(p.id)}</span></div><h2>${esc(p.title)}</h2>${p.description ? `<p>${esc(p.description)}</p>` : ""}</div>
      <div class="sub" role="tablist">${subs.map(([k, l]) => `<button role="tab" data-ssub="${k}" aria-selected="${this.s.scanSub === k}">${l}</button>`).join("")}</div><div class="db">${body}</div>`;
  }

  // ------------------------------------------------------------ installed tab
  vInstalled() {
    const inst = this.s.settings?.installed || {};
    const ids = Object.keys(inst);
    if (!ids.length) return `<div class="card empty">Aucun package installé depuis la bibliothèque sur cette instance.</div>`;
    const libById = Object.fromEntries((this.s.lib?.packages || []).map((p) => [p.id, p]));
    return `<div class="list">${ids.sort().map((id) => {
      const r = inst[id]; const lp = libById[id];
      const upd = lp && lp.version !== r.version && this.s.source === r.source;
      return `<div class="card"><div class="row" style="justify-content:space-between"><div><h3 style="margin:0;font-size:15px;font-weight:500">${esc(r.title || id)}</h3>
        <div class="counts">Installé le ${fmtDate(r.installed_at)} · version ${esc(r.version)} · <span class="ref">${esc(r.file)}</span></div></div>
        <div class="row">${upd ? `<span class="chip warn">nouvelle version ${esc(lp.version)}</span><button class="btn small primary" data-update="${esc(id)}">Mettre à jour…</button>` : ""}
        <button class="btn small danger" data-uninstall="${esc(id)}">Désinstaller</button></div></div>
        ${(r.skipped || []).length ? `<div class="note" style="margin-top:8px">Conservés car déjà présents : ${r.skipped.map(esc).join(", ")}</div>` : ""}
        ${(r.files || []).length ? `<div class="counts" style="margin-top:6px">Fichiers : ${r.files.map(esc).join(", ")}</div>` : ""}</div>`;
    }).join("")}</div>`;
  }

  // ------------------------------------------------------------ settings tab
  vSettings() {
    const st = this.s.settings || {};
    const gh = (st.sources || []).filter((x) => x.type === "github");
    return `<div class="list">
      <section class="card"><h2 style="margin:0 0 10px;font-size:17px;font-weight:500">Cette instance</h2>
        <div class="form"><label>Nom affiché dans la bibliothèque<input type="text" id="set-name" value="${esc(st.instance_name || "")}"></label></div>
        <div class="row" style="margin-top:10px"><button class="btn primary small" data-act="save-name">Enregistrer</button></div></section>
      <section class="card"><h2 style="margin:0 0 6px;font-size:17px;font-weight:500">Dépôts GitHub</h2>
        <p class="counts" style="margin:0 0 10px">Un dépôt GitHub sert de bibliothèque centrale : chaque instance l’ajoute comme source pour installer, et une instance peut y publier ses exports. Pour un dépôt privé ou pour publier, créez un jeton « fine-grained » avec l’accès <b>Contents: Read and write</b> sur ce seul dépôt.</p>
        ${gh.length ? `<div class="tw"><table><thead><tr><th>Dépôt</th><th>Branche</th><th>Dossier</th><th>Jeton</th><th>Publication</th><th></th></tr></thead><tbody>${gh.map((g) => `<tr><td class="m">${esc(g.repo)}</td><td class="m">${esc(g.branch)}</td><td class="m">${esc(g.path || "/")}</td><td>${g.has_token ? '<span class="chip ok">enregistré</span>' : '<span class="chip">aucun</span>'}</td>
          <td><input type="radio" name="pub" data-pub="${esc(g.id)}" ${st.publish_to === g.id ? "checked" : ""} aria-label="Publier vers ${esc(g.repo)}"></td><td><button class="btn small danger" data-rmsrc="${esc(g.id)}">Retirer</button></td></tr>`).join("")}</tbody></table></div>` : ""}
        <div class="form" style="margin-top:10px"><label>Dépôt (propriétaire/nom)<input type="text" id="gh-repo" name="lib-repo" autocomplete="off" placeholder="proprietaire/bibliotheque-ha" value="${esc(gh[0]?.repo || "")}"></label><label>Branche<input type="text" id="gh-branch" name="lib-branch" autocomplete="off" value="${esc(gh[0]?.branch || "main")}"></label>
          <label>Dossier dans le dépôt (optionnel)<input type="text" id="gh-path" name="lib-path" autocomplete="off" placeholder="ex. library" value="${esc(gh[0]?.path || "")}"></label><label>Jeton GitHub (commence par github_pat_)<input type="password" id="gh-token" name="lib-gh-token" autocomplete="new-password" data-lpignore="true" data-1p-ignore="true" placeholder="github_pat_…"></label></div>
        <div class="row" style="margin-top:10px"><button class="btn primary small" data-act="add-gh">Ajouter / mettre à jour</button>${st.publish_to ? `<button class="btn small" data-act="nopub">Ne plus publier</button>` : ""}</div></section>
      <section class="card"><h2 style="margin:0 0 6px;font-size:17px;font-weight:500">Règles de regroupement</h2>
        <p class="counts" style="margin:0 0 10px">Sans règle, les packages sont formés par catégorie HA, puis par préfixe commun des noms (« Dreame • … »), puis par éléments qui partagent des helpers. Les règles permettent de forcer un regroupement, un titre et des contextes.</p>
        <textarea id="rules" spellcheck="false">${esc(st.rules || "")}</textarea>
        <div class="row" style="margin-top:10px"><button class="btn primary small" data-act="save-rules">Enregistrer les règles</button><span class="counts">Relancez le scan pour les appliquer.</span></div></section>
    </div>`;
  }

  // ------------------------------------------------------------ install modal
  async openInstall(ids, force = false) {
    this.s.modal = { ids, force, plan: null, mapping: {}, secrets: {}, enable: false, busy: true, result: null, error: null };
    this.renderModal();
    await this.replan();
  }

  async replan() {
    const m = this.s.modal; if (!m) return;
    m.busy = true; this.renderModal();
    try {
      m.plan = await this.ws("plan", { source_id: this.s.source, package_ids: m.ids, mapping: m.mapping });
      for (const e of [...m.plan.entities, ...m.plan.notify]) if (e.target && !(e.entity_id in m.mapping)) m.mapping[e.entity_id] = e.target;
      m.error = null;
    } catch (e) { m.error = e.message || String(e); }
    m.busy = false; this.renderModal();
  }

  renderModal() {
    const host = this.shadowRoot.getElementById("modal");
    const m = this.s.modal;
    if (this.s.bp && !this.s.confirm) {
      const b = this.s.bp;
      host.innerHTML = `<div class="modal"><div class="box" role="dialog" aria-modal="true"><div class="mh"><h2>Blueprint</h2><button class="btn small" data-act="bp-close">Fermer</button></div>
        <div class="mb">${b.error ? `<div class="note bad">${esc(b.error)}</div>` : !b.yaml ? `<div class="empty"><span class="spin"></span></div>` : `
          <div class="note">${b.inputs} champ(s) à choisir lors de l’utilisation : chaque entité, appareil et notification devient un réglage du blueprint. Utilisable sur n’importe quelle instance via Paramètres → Automatisations → Blueprints.</div>
          ${b.unconverted.length ? `<div class="note warn">Restent en dur dans un template (à vérifier) : ${b.unconverted.map(esc).join(", ")}</div>` : ""}
          ${b.saved ? `<div class="note ok">Enregistré dans <code>${esc(b.saved)}</code>. Il apparaît dans Paramètres → Automatisations et scènes → Blueprints.</div>` : ""}
          <div class="form"><label>Nom du fichier<input type="text" id="bp-file" value="${esc(b.filename)}"></label></div>
          <pre>${this.hl(b.yaml)}</pre>`}</div>
        <div class="mf">${b.yaml ? `<button class="btn" data-act="bp-copy">Copier</button><button class="btn primary" data-act="bp-save" ${b.saved ? "disabled" : ""}>Enregistrer sur cette instance</button>` : ""}</div></div></div>`;
      return;
    }
    if (this.s.ghosts && !this.s.confirm) {
      const g = this.s.ghosts;
      host.innerHTML = `<div class="modal"><div class="box" role="dialog" aria-modal="true"><div class="mh"><h2>Entrées fantômes du registre</h2><button class="btn small" data-act="ghosts-close">Fermer</button></div>
        <div class="mb"><div class="note">Ces automatisations, scripts et scènes n’existent plus dans la configuration mais restent dans le registre des entités (état « indisponible »). Les retirer ne supprime aucun code. Si l’un d’eux est seulement en erreur (YAML invalide), corrigez-le plutôt : il reviendrait avec un nouvel identifiant d’entité.</div>
        <div class="row"><button class="btn small" data-act="ghosts-all">Tout cocher</button><button class="btn small" data-act="ghosts-none">Tout décocher</button><span class="counts">${g.sel.size} / ${g.list.length} sélectionnée(s)</span></div>
        <div class="tw"><table><tbody>${g.list.map((x) => `<tr><td style="width:28px"><input type="checkbox" data-ghost="${esc(x.entity_id)}" ${g.sel.has(x.entity_id) ? "checked" : ""} aria-label="Retirer ${esc(x.entity_id)}"></td><td>${esc(x.name)}</td><td class="m">${esc(x.entity_id)}</td></tr>`).join("")}</tbody></table></div></div>
        <div class="mf"><button class="btn danger" data-act="ghosts-remove" ${g.sel.size ? "" : "disabled"}>Retirer ${g.sel.size} entrée(s) du registre</button></div></div></div>`;
      return;
    }
    if (this.s.confirm) {
      const c = this.s.confirm;
      host.innerHTML = `<div class="modal" data-act="noop"><div class="box" style="width:min(480px,100%)"><div class="mh"><h2>${esc(c.title)}</h2></div><div class="mb"><p style="margin:0">${esc(c.text)}</p></div>
        <div class="mf"><button class="btn" data-act="confirm-no">Annuler</button><button class="btn ${c.danger ? "danger" : "primary"}" data-act="confirm-yes">${esc(c.ok)}</button></div></div></div>`;
      return;
    }
    if (!m) { host.innerHTML = ""; return; }
    const p = m.plan;
    let body = "";
    if (m.result) {
      const r = m.result;
      body = `<div class="note ok"><b>${r.installed.length ? "Installé" : "Rien à installer"}</b> ${r.installed.map(esc).join(", ")}${r.skipped_up_to_date?.length ? `<br>Déjà à jour : ${r.skipped_up_to_date.map(esc).join(", ")}` : ""}</div>
        ${r.reloaded?.length ? `<div class="counts">Rechargé sans redémarrer : ${r.reloaded.map(esc).join(", ")}</div>` : ""}
        ${r.packages_enabled_now ? `<div class="note warn">Les packages viennent d’être activés dans configuration.yaml (une sauvegarde a été créée). Un redémarrage est nécessaire pour que tout soit pris en compte.</div>` : ""}
        ${r.restart_required && !r.packages_enabled_now ? `<div class="note warn">Certaines sections ne se rechargent pas à chaud : redémarrez Home Assistant.</div>` : ""}
        ${Object.values(r.records || {}).some((x) => x.skipped?.length) ? `<div class="note">Conservés car déjà présents : ${Object.values(r.records).flatMap((x) => x.skipped).map(esc).join(", ")}</div>` : ""}`;
    } else if (!p) {
      body = m.error ? `<div class="note bad">${esc(m.error)}</div>` : `<div class="empty"><span class="spin"></span> Analyse de l’instance…</div>`;
    } else {
      const st = { "chargée": "ok", "à configurer": "warn", absente: "bad" };
      const order = p.packages.map((x) => `<span class="chip">${esc(x.title)}${x.explicit ? "" : " · dépendance"}${x.installed_version ? (x.installed_version === x.version ? " · à jour" : " · mise à jour") : ""}</span>`).join("");
      const entRows = p.entities.map((e) => {
        const dom = e.entity_id.split(".")[0];
        const list = `dl-${dom}`;
        return `<tr><td class="m">${esc(e.entity_id)}</td><td>${e.exists && !m.mapping[e.entity_id] ? '<span class="chip ok">présente</span>' : `<input type="text" list="${list}" data-map="${esc(e.entity_id)}" value="${esc(m.mapping[e.entity_id] || "")}" placeholder="${esc(dom)}.…">
          ${e.suggestions?.length ? `<div class="sug">${e.suggestions.map((s) => `<button data-sug="${esc(e.entity_id)}" data-val="${esc(s.entity_id)}" title="${esc(s.name)}">${esc(s.entity_id)}</button>`).join("")}</div>` : ""}`}</td></tr>`;
      }).join("");
      const domains = [...new Set(p.entities.map((e) => e.entity_id.split(".")[0]))];
      const datalists = domains.map((d) => `<datalist id="dl-${d}">${Object.keys(this._hass.states).filter((x) => x.startsWith(d + ".")).slice(0, 400).map((x) => `<option value="${x}">`).join("")}</datalist>`).join("");
      const notifRows = p.notify.map((n) => `<tr><td class="m">${esc(n.entity_id)}</td><td>${n.exists && !m.mapping[n.entity_id] ? '<span class="chip ok">présent</span>' : `<select data-map="${esc(n.entity_id)}"><option value="">— choisir —</option>${n.suggestions.map((s) => `<option value="${esc(s.entity_id)}" ${m.mapping[n.entity_id] === s.entity_id ? "selected" : ""}>${esc(s.entity_id)}</option>`).join("")}</select>`}</td></tr>`).join("");
      const secRows = p.secrets.filter((s) => !s.exists).map((s) => `<tr><td class="m">${esc(s.name)}</td><td><input type="password" autocomplete="off" data-secret="${esc(s.name)}" value="${esc(m.secrets[s.name] || "")}" placeholder="valeur écrite dans secrets.yaml"></td></tr>`).join("");
      const missingEnt = p.entities.filter((e) => !e.exists && !m.mapping[e.entity_id]).length;
      const allDevs = Object.values(this._hass.devices || {}).map((x) => ({ id: x.id, name: x.name_by_user || x.name || x.id, model: x.model })).sort((a, b) => a.name.localeCompare(b.name));
      const devRows = (p.devices || []).map((dv) => {
        if (dv.exists && !m.mapping[dv.id]) return `<tr><td>${esc(dv.name)}<div class="counts">${esc([dv.manufacturer, dv.model].filter(Boolean).join(" · "))}</div></td><td><span class="chip ok">présent</span></td></tr>`;
        const sugIds = new Set(dv.suggestions.map((x) => x.id));
        const opt = (x) => `<option value="${esc(x.id)}" ${m.mapping[dv.id] === x.id ? "selected" : ""}>${esc(x.name)}${x.model ? " · " + esc(x.model) : ""}</option>`;
        return `<tr><td>${esc(dv.name)}<div class="counts">${esc([dv.manufacturer, dv.model].filter(Boolean).join(" · ") || "modèle inconnu")}</div></td><td><select data-map="${esc(dv.id)}"><option value="">— choisir un appareil —</option>
          ${dv.suggestions.length ? `<optgroup label="Suggestions">${dv.suggestions.map(opt).join("")}</optgroup>` : ""}<optgroup label="Tous les appareils">${allDevs.filter((x) => !sugIds.has(x.id)).map(opt).join("")}</optgroup></select></td></tr>`;
      }).join("");
      body = `${m.error ? `<div class="note bad">${esc(m.error)}</div>` : ""}
        ${p.blocking.length ? `<div class="note bad">${p.blocking.map(esc).join("<br>")}</div>` : ""}
        ${(p.warnings || []).length ? `<div class="note warn">${p.warnings.map(esc).join("<br>")}</div>` : ""}
        <div class="sec"><span class="label">Ordre d’installation</span><div class="row">${order}</div></div>
        <div class="sec"><span class="label">Intégrations</span><div class="row">${Object.entries(p.integrations).map(([k, v]) => `<span class="chip ${st[v]}">${esc(k)} · ${v}</span>`).join("") || '<span class="counts">Aucune en dehors du cœur de HA</span>'}</div></div>
        ${p.entities.length ? `<div class="sec"><span class="label">Correspondance des entités (${missingEnt} à choisir)</span><div class="tw"><table><thead><tr><th style="width:42%">Dans le package</th><th>Sur cette instance</th></tr></thead><tbody>${entRows}</tbody></table></div>${datalists}
          <div class="counts">Une entité laissée vide est écrite telle quelle : l’automatisation fonctionnera dès que cette entité existera.</div></div>` : ""}
        ${p.notify.length ? `<div class="sec"><span class="label">Notifications</span><div class="tw"><table><tbody>${notifRows}</tbody></table></div></div>` : ""}
        ${secRows ? `<div class="sec"><span class="label">Secrets à renseigner</span><div class="tw"><table><tbody>${secRows}</tbody></table></div></div>` : ""}
        ${p.conflicts.length ? `<div class="note warn"><b>Déjà présent sur cette instance</b><br>${p.conflicts.map((c) => `${esc(c.what)} : ${esc(c.reason)}`).join("<br>")}</div>` : ""}
        ${p.files.length ? `<div class="counts">Fichiers ajoutés : ${p.files.map((f) => esc(f.path) + (f.exists ? " (existe, conservé)" : "")).join(", ")}</div>` : ""}
        ${!p.packages_setup.enabled && p.packages_setup.editable ? `<label class="note warn" style="display:flex;gap:8px;align-items:flex-start;cursor:pointer"><input type="checkbox" id="enable-pk" ${m.enable ? "checked" : ""}> <span>Activer les packages dans configuration.yaml (ajoute <code>packages: !include_dir_named packages</code> sous <code>homeassistant:</code>, avec une sauvegarde du fichier). Nécessaire pour installer.</span></label>` : ""}
        ${devRows ? `<div class="sec"><span class="label">Appareils</span><div class="tw"><table><thead><tr><th style="width:42%">Dans le package</th><th>Sur cette instance</th></tr></thead><tbody>${devRows}</tbody></table></div>
          <div class="counts">Un appareil laissé vide garde l’identifiant d’origine : le déclencheur restera inactif jusqu’à ce que vous le refassiez dans l’éditeur.</div></div>` : ""}`;
    }
    const canInstall = p && !m.result && !p.blocking.length && (p.packages_setup.enabled || m.enable) && !m.busy;
    host.innerHTML = `<div class="modal"><div class="box" role="dialog" aria-modal="true"><div class="mh"><h2>${m.result ? "Installation terminée" : "Installer depuis la bibliothèque"}</h2><button class="btn small" data-act="close">Fermer</button></div>
      <div class="mb">${body}</div>
      <div class="mf">${m.result ? (m.result.restart_required || m.result.packages_enabled_now ? `<button class="btn primary" data-act="restart">Redémarrer Home Assistant</button>` : "") :
        `${p ? `<button class="btn" data-act="replan" ${m.busy ? "disabled" : ""}>${m.busy ? '<span class="spin"></span>' : ""}Vérifier à nouveau</button>` : ""}<button class="btn primary" data-act="do-install" ${canInstall ? "" : "disabled"}>Installer</button>`}</div></div></div>`;
  }

  // ------------------------------------------------------------ events
  async onClick(e) {
    const t = e.target.closest("button,[data-pkg],[data-spkg],input.pick,input[data-pub],input[data-ghost]");
    if (!t) return;
    const d = t.dataset;
    if (t.matches("input.pick") && d.pick) { d.pick && (t.checked ? this.s.cart.add(d.pick) : this.s.cart.delete(d.pick)); e.stopPropagation(); this.render(); return; }
    if (t.matches("input.pick") && d.incl) { e.stopPropagation(); return this.override({ package_id: d.incl, exclude: !t.checked }); }
    if (d.ghost) { t.checked ? this.s.ghosts.sel.add(d.ghost) : this.s.ghosts.sel.delete(d.ghost); return this.renderModal(); }
    if (d.pub) { return this.saveSettings({ publish_to: d.pub }, "Les exports seront publiés sur ce dépôt"); }
    if (d.tab) { this.s.tab = d.tab; this.render(); return; }
    if (d.act === "menu") { this.dispatchEvent(new Event("hass-toggle-menu", { bubbles: true, composed: true })); return; }
    if (d.lv) { this.s.libView = d.lv; if (d.lv === "views" && !this._dashes) { try { this._dashes = await this.ws("dashboards"); } catch (_) { this._dashes = []; } } this.render(); return; }
    if (d.ctx !== undefined && t.closest(".seg")) { this.s.ctx = d.ctx; this.render(); return; }
    if (d.pkg) { this.s.sel = d.pkg; this.render(); return; }
    if (d.spkg) { this.s.scanSel = d.spkg; this.render(); return; }
    if (d.sub) { this.s.sub = d.sub; this.render(); return; }
    if (d.ssub) { this.s.scanSub = d.ssub; this.render(); return; }
    if (d.install) { return this.openInstall([d.install], !!this.s.lib.packages.find((p) => p.id === d.install)?.installed); }
    if (d.update) { this.s.tab = "library"; this.s.source = this.s.settings.installed[d.update].source || "local"; await this.loadLibrary(); return this.openInstall([d.update], true); }
    if (d.uninstall) { return this.ask("Désinstaller ce package ?", "Son fichier est supprimé du dossier packages et les domaines concernés sont rechargés. Les secrets ajoutés restent dans secrets.yaml.", "Désinstaller", true, () => this.uninstall(d.uninstall)); }
    if (d.copy === "pkg") { return this.copy(this.s.pkgCache[this.s.sel]?.yaml || ""); }
    if (d.copyView) { const r = await this.ws("view", { source_id: this.s.source, view_id: d.copyView }); return this.copy(r.yaml); }
    if (d.sug) { this.s.modal.mapping[d.sug] = d.val; this.renderModal(); return; }
    if (d.rmsrc) { return this.saveSettings({ remove_source: d.rmsrc }, "Dépôt retiré"); }
    if (d.bp) {
      this.s.bp = { yaml: "" }; this.renderModal();
      const args = this.s.tab === "library" ? { item_uid: d.bp, source_id: this.s.source, package_id: this.s.sel } : { item_uid: d.bp };
      try { this.s.bp = { ...(await this.ws("blueprint", args)), saved: null }; } catch (err) { this.s.bp = { error: err.message || String(err) }; }
      return this.renderModal();
    }
    if (d.addview) {
      const sel = this.shadowRoot.querySelector(`[data-dash-for="${CSS.escape(d.addview)}"]`);
      const dash = sel?.value; const title = this._dashes.find((x) => x.url_path === dash)?.title || dash;
      return this.ask("Ajouter cette vue ?", `Elle sera ajoutée à la fin du dashboard « ${title} ». Une sauvegarde du dashboard est faite avant.`, "Ajouter", false, async () => {
        const r = await this.ws("view/install", { source_id: this.s.source, view_id: d.addview, dashboard: dash });
        this.toast(`Vue ajoutée (onglet « ${r.path} »)` + (r.missing_cards.length ? `\nCartes à installer via HACS : ${r.missing_cards.join(", ")}` : "") + (r.missing_entities.length ? `\n${r.missing_entities.length} entité(s) absente(s) sur cette instance` : ""), 8000);
      });
    }
    if (d.unmove) { return this.override({ item_uid: d.unmove, move_to: null }); }
    switch (d.act) {
      case "refresh": return this.refresh();
      case "clearcart": this.s.cart.clear(); return this.render();
      case "install-cart": return this.openInstall([...this.s.cart]);
      case "lib-remove": return this.ask("Retirer ce package de la bibliothèque locale ?", "Les installations existantes ne sont pas touchées.", "Retirer", true, async () => { await this.ws("library/remove", { package_id: d.id }); this.toast("Retiré de la bibliothèque"); await this.loadLibrary(); });
      case "scan": return this.scan();
      case "export": return this.exportLocal();
      case "publish": return this.publish();
      case "save-ov": {
        const r = this.shadowRoot;
        return this.override({ package_id: d.id, title: r.getElementById("ov-title").value, description: r.getElementById("ov-desc").value, contexts: [...r.querySelectorAll(".ov-ctx:checked")].map((x) => x.value) }, "Enregistré");
      }
      case "save-name": return this.saveSettings({ instance_name: this.shadowRoot.getElementById("set-name").value }, "Nom enregistré");
      case "save-rules": return this.saveSettings({ rules: this.shadowRoot.getElementById("rules").value }, "Règles enregistrées");
      case "nopub": return this.saveSettings({ publish_to: null }, "Publication désactivée");
      case "add-gh": {
        const r = this.shadowRoot;
        const token = r.getElementById("gh-token").value.trim();
        if (token && !/^(github_pat_|ghp_|gho_|ghs_)/.test(token)) { this.toast("Ce jeton ne ressemble pas à un jeton GitHub (il doit commencer par github_pat_). Si le navigateur a rempli le champ tout seul, videz-le et collez le jeton.", 8000); return; }
        await this.saveSettings({ source: { repo: r.getElementById("gh-repo").value, branch: r.getElementById("gh-branch").value, path: r.getElementById("gh-path").value, token } }, "Dépôt enregistré");
        return;
      }
      case "close": this.s.modal = null; this.renderModal(); return this.loadLibrary().then(() => this.refreshSettings());
      case "replan": return this.replan();
      case "do-install": return this.install();
      case "restart": return this.ask("Redémarrer Home Assistant ?", "L’interface sera indisponible pendant le redémarrage.", "Redémarrer", false, () => this._hass.callService("homeassistant", "restart"));
      case "bp-close": this.s.bp = null; return this.renderModal();
      case "bp-copy": return this.copy(this.s.bp.yaml);
      case "bp-save": {
        const b = this.s.bp; const filename = this.shadowRoot.getElementById("bp-file").value || b.filename;
        try { const r = await this.ws("blueprint/save", { yaml: b.yaml, domain: b.domain, filename }); b.saved = r.path; }
        catch (err) { this.err(err); }
        return this.renderModal();
      }
      case "ghosts": { const list = await this.ws("ghosts"); this.s.ghosts = { list, sel: new Set(list.map((x) => x.entity_id)) }; return this.renderModal(); }
      case "ghosts-close": this.s.ghosts = null; return this.renderModal();
      case "ghosts-all": this.s.ghosts.sel = new Set(this.s.ghosts.list.map((x) => x.entity_id)); return this.renderModal();
      case "ghosts-none": this.s.ghosts.sel = new Set(); return this.renderModal();
      case "ghosts-remove": { const ids = [...this.s.ghosts.sel]; return this.ask("Retirer ces entrées du registre ?", `${ids.length} entrée(s) seront retirées. Aucun fichier de configuration n’est modifié.`, "Retirer", true, async () => { const r = await this.ws("ghosts/remove", { entity_ids: ids }); this.s.ghosts = null; this.renderModal(); this.toast(`${r.removed.length} entrée(s) retirée(s)`); await this.scan(); }); }
      case "confirm-no": this.s.confirm = null; return this.renderModal();
      case "confirm-yes": { const fn = this.s.confirm.fn; this.s.confirm = null; this.renderModal(); try { await fn(); } catch (err) { this.err(err); } return; }
    }
  }

  onInput(e) {
    const t = e.target;
    if (t.dataset.k === "q") { this.s.q = t.value; const pos = t.selectionStart; this.render(); const n = this.shadowRoot.querySelector('[data-k="q"]'); n.focus(); n.setSelectionRange(pos, pos); return; }
    if (t.dataset.map !== undefined && this.s.modal) { this.s.modal.mapping[t.dataset.map] = t.value.trim(); }
    if (t.dataset.secret !== undefined && this.s.modal) { this.s.modal.secrets[t.dataset.secret] = t.value; }
  }

  async onChange(e) {
    const t = e.target;
    if (t.dataset.k === "source") { this.s.source = t.value; this.s.sel = null; this.s.cart.clear(); return this.loadLibrary(); }
    if (t.dataset.k === "integ") { this.s.integ = t.value; return this.render(); }
    if (t.id === "enable-pk" && this.s.modal) { this.s.modal.enable = t.checked; return this.renderModal(); }
    if (t.dataset.map !== undefined && this.s.modal && t.tagName === "SELECT") { this.s.modal.mapping[t.dataset.map] = t.value; return; }
    if (t.dataset.move) {
      let target = t.value;
      if (!target) return;
      if (target === "__new__") {
        target = (window.prompt && window.prompt("Nom du nouveau package")) || "";
        if (!target) { t.value = ""; return; }
      }
      return this.override({ item_uid: t.dataset.move, move_to: target }, "Élément déplacé");
    }
  }

  async onToggle(e) {
    const det = e.target;
    if (!(det instanceof HTMLElement) || !det.open) return;
    const pre = det.querySelector("pre[data-view-yaml]");
    if (pre && pre.textContent === "Ouverture…") {
      try { const r = await this.ws("view", { source_id: this.s.source, view_id: pre.dataset.viewYaml }); pre.innerHTML = this.hl(r.yaml); } catch (err) { pre.textContent = err.message; }
    }
  }

  ask(title, text, ok, danger, fn) { this.s.confirm = { title, text, ok, danger, fn }; this.renderModal(); }

  async copy(txt) {
    try { await navigator.clipboard.writeText(txt); this.toast("Copié dans le presse-papiers"); }
    catch (_) { const ta = document.createElement("textarea"); ta.value = txt; this.shadowRoot.appendChild(ta); ta.select(); try { document.execCommand("copy"); this.toast("Copié"); } catch (__) { this.toast("Copie impossible : sélectionnez le texte"); } ta.remove(); }
  }

  // ------------------------------------------------------------ actions
  async refreshSettings() { try { this.s.settings = await this.ws("settings/get"); } catch (e) { this.err(e); } this.render(); }
  async saveSettings(data, msg) {
    try { const s = await this.ws("settings/set", data); this.s.settings = { ...this.s.settings, ...s }; this.toast(msg); } catch (e) { this.err(e); }
    this.render();
  }
  async refresh() {
    this.s.busy = "refresh"; this.render();
    try { const r = await this.ws("source/refresh", { source_id: this.s.source }); this.toast(`${r.files} fichiers téléchargés`); await this.refreshSettings(); }
    catch (e) { this.err(e); }
    this.s.busy = null; await this.loadLibrary();
  }
  async scan() {
    this.s.busy = "scan"; this.render();
    try { this.s.scan = await this.ws("scan"); this.toast(`${this.s.scan.packages.length} packages proposés`); } catch (e) { this.err(e); }
    this.s.busy = null; this.render();
  }
  async override(data, msg) {
    try { this.s.scan = await this.ws("override", data); if (msg) this.toast(msg); } catch (e) { this.err(e); }
    this.render();
  }
  async exportLocal() {
    const ids = (this.s.scan?.packages || []).filter((p) => !p.exclude).map((p) => p.id);
    if (!ids.length) return this.toast("Aucun package coché à exporter");
    this.s.busy = "export"; this.render();
    try {
      const r = await this.ws("export", { package_ids: ids });
      this.toast(`${r.written.length} packages enregistrés dans la bibliothèque locale${Object.keys(r.renamed || {}).length ? " (certains renommés pour éviter un doublon)" : ""}`, 4000);
      if (this.s.source === "local") await this.loadLibrary();
    } catch (e) { this.err(e); }
    this.s.busy = null; this.render();
  }
  async publish() {
    this.s.busy = "publish"; this.render();
    try { const r = await this.ws("publish", { source_id: this.s.settings.publish_to }); this.toast(`Publié : ${r.files} fichiers, commit ${r.commit.slice(0, 7)}`, 5000); }
    catch (e) { this.err(e); }
    this.s.busy = null; this.render();
  }
  async install() {
    const m = this.s.modal; m.busy = true; this.renderModal();
    try {
      m.result = await this.ws("install", { source_id: this.s.source, package_ids: m.ids, mapping: m.mapping, secrets: m.secrets, enable_packages: m.enable, force_update: m.force });
      this.s.cart.clear();
    } catch (e) { m.error = e.message || String(e); }
    m.busy = false; this.renderModal();
  }
  async uninstall(id) {
    try { const r = await this.ws("uninstall", { package_id: id }); this.toast(`Désinstallé${r.registry_cleaned?.length ? `, ${r.registry_cleaned.length} entrée(s) du registre nettoyée(s)` : ""}${r.restart_required ? ". Redémarrage conseillé." : ""}`, 4500); }
    catch (e) { this.err(e); }
    await this.refreshSettings(); await this.loadLibrary();
  }
}

customElements.define("ha-library-panel", HaLibraryPanel);

  import * as vscode from "vscode";
  import { EditTracker } from "./editTracker";

  export class BDDPanel {
    private currentFilePath: string | null = null;
    static currentPanel: BDDPanel | undefined;
    private readonly panel: vscode.WebviewPanel;
    private featureText: string = "";
    private isPlaceholder: boolean = true;
    private readonly editTracker: EditTracker;

    setFilePath(filePath: string | null) {
      this.currentFilePath = filePath;
      if(filePath) {
        this.panel.webview.postMessage({ type: "enableHistory", enabled: true });
      }
      else {
        this.panel.webview.postMessage({ type: "enableHistory", enabled: false });
      }
    }

    private constructor(panel: vscode.WebviewPanel, featureText: string, editTracker: EditTracker) {
      this.panel = panel;
      this.featureText = featureText;
      this.editTracker = editTracker;
      this.panel.webview.html = this.getHtml(featureText);

      this.panel.webview.onDidReceiveMessage(async (message) => {
        switch (message.type) {
          case "viewHistory": {
            if (!this.currentFilePath) return;

            const entries = this.editTracker.getFileHistory(this.currentFilePath);

            this.panel.webview.postMessage({
              type: "historyData",
              entries
            });
            break;
          }
          case "restoreHistory": {
            if (!this.currentFilePath) return;

            const entry = this.editTracker.getFileHistory(this.currentFilePath)[message.index];
            if (!entry) return;

            // 1️⃣ Restore editor + disk
            this.featureText = entry.contentSnapshot;

            // Optional: write back to file
            const uri = vscode.Uri.file(this.currentFilePath);
            await vscode.workspace.fs.writeFile(
              uri,
              Buffer.from(entry.contentSnapshot, "utf8")
            );

            // 2️⃣ Log restore as a new edit
            this.editTracker.logEdit(
              this.currentFilePath,
              "restore",
              entry.contentSnapshot,
              "manual_edit"
            );

            // 3️⃣ Update webview UI
            this.panel.webview.postMessage({
              type: "setFeatureText",
              text: entry.contentSnapshot
            });

            vscode.window.showInformationMessage("✅ Version restored");
            break;
          }
          case "updateText":
            this.featureText = message.text;
            break;
          case "run":
            if (!this.isPlaceholder && this.featureText){
              vscode.commands.executeCommand(
                "extension.executeBDD",
                this.featureText,
                BDDPanel.currentPanel);
            } 
            else {
              vscode.window.showErrorMessage("❌ Cannot Run: No featureText detected.");
            }
            break;
          case "generateBDD":
            vscode.commands.executeCommand("extension.generateBDD");
            break;
          case "save":
            if (this.currentFilePath) {
              vscode.commands.executeCommand(
                "extension.saveThisFeature",
                this.currentFilePath,
                this.featureText
              );
            } else {
              vscode.window.showErrorMessage("❌ Cannot save: No file path detected.");
            }
            break;
          case "saveVersion":
            vscode.commands.executeCommand("extension.saveVersionFolder");
            break;
          }
        },
        undefined,
        []
      );

      this.panel.onDidDispose(() => this.dispose());
    }

    static show(featureText: string, isPlaceholder: boolean = false, editTracker: EditTracker): BDDPanel {
      if (BDDPanel.currentPanel) {
        BDDPanel.currentPanel.panel.reveal(vscode.ViewColumn.One);
        BDDPanel.currentPanel.update(featureText, isPlaceholder);
        return BDDPanel.currentPanel;
      }

      const panel = vscode.window.createWebviewPanel(
        "bddPreview",
        "AI-Generated BDD Tests",
        vscode.ViewColumn.One,
        {
          enableScripts: true,
          retainContextWhenHidden: true,
        }
      );

      BDDPanel.currentPanel = new BDDPanel(panel, featureText, editTracker);
      BDDPanel.currentPanel.update(featureText, isPlaceholder);
      return BDDPanel.currentPanel;
    }

    getFeatureText(): string {
      return this.featureText;
    }

    showOutput(output: string) {
      this.panel.webview.postMessage({ type: "output", output });
    }

    private update(featureText: string, isPlaceholder: boolean = false) {
      this.featureText = featureText;
      this.isPlaceholder = isPlaceholder;
      this.panel.webview.html = this.getHtml(featureText);
    }

    private dispose() {
      BDDPanel.currentPanel = undefined;
      this.panel.dispose();
    }

    private getHtml(featureText: string): string {
      const escaped = featureText
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(
          /(Feature:|Scenario:|Given |When |Then |And )/g,
          `<span class="keyword">$1</span>`
        );

      return /* html */ `
  <!DOCTYPE html>
  <html lang="en">
  <head>
  <meta charset="UTF-8" />
  <title>AI-Generated BDD Tests</title>

  <style>
  :root { color-scheme: light dark; }

  body {
    font-family: var(--vscode-editor-font-family);
    font-size: var(--vscode-editor-font-size);
    background: var(--vscode-editor-background);
    color: var(--vscode-editor-foreground);
    padding: 16px;
  }

  pre {
    border: 1px solid var(--vscode-editorWidget-border);
    border-radius: 6px;
    padding: 12px;
    height: 60vh;
    overflow-y: auto;
  }

  .keyword {
    color: var(--vscode-editor-keywordForeground, #c586c0);
    font-weight: bold;
  }

  button {
    background: var(--vscode-button-background);
    color: var(--vscode-button-foreground);
    border: none;
    padding: 8px 16px;
    border-radius: 6px;
    cursor: pointer;
  }

  button:hover {
    background: var(--vscode-button-hoverBackground);
  }

  #output {
    margin-top: 15px;
    border: 1px solid var(--vscode-editorWidget-border);
    border-radius: 6px;
    height: 60vh;
    overflow-y: auto;
  }

  .button-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-top: 8px;
    gap: 12px;
  }

  .left-buttons,
  .right-buttons {
    display: flex;
    gap: 10px;
  }

  .top-right-btn {
    position: absolute;
    top: 16px;
    right: 16px;
  }

  /* 🔎 VS CODE SEARCH POPUP */
  .search-popup {
    position: absolute;
    top: 8px;
    right: 8px;
    background: var(--vscode-editorWidget-background);
    border: 1px solid var(--vscode-editorWidget-border);
    border-radius: 6px;
    padding: 6px 8px;
    display: none;
    align-items: center;
    gap: 8px;
    z-index: 10;
  }

  .search-popup input {
    width: 220px;
    height: 28px;
    background: var(--vscode-input-background);
    color: var(--vscode-input-foreground);
    border: 1px solid var(--vscode-input-border);
    border-radius: 4px;
    padding: 0 8px;
  }

  .search-popup button {
    height: 28px;
    width: 28px;
    border-radius: 4px;
    border: none;
    background: var(--vscode-button-background);
    color: var(--vscode-button-foreground);
    align-items: center;
    justify-content: center;
    display: flex;
    cursor: pointer;
  }

  .match-count {
    font-size: 12px;
    opacity: 0.8;
  }

  /* 🔦 MATCH HIGHLIGHT */
  .search-match {
    background: #ffe066;
    color: #000;
  }

  .search-match.active {
    background: #ffbf00;
  }

  .history-entry {
    border-left: 3px solid var(--vscode-editorWidget-border);
    padding-left: 10px;
    margin-bottom: 12px;
  }

  .history-meta {
    font-size: 12px;
    opacity: 0.8;
  }

  .badge {
    padding: 2px 6px;
    border-radius: 10px;
    font-size: 11px;
    margin-right: 6px;
  }

  .badge.manual_edit { background: #4caf50; color: #fff; }
  .badge.ai_generated { background: #2196f3; color: #fff; }
  .badge.external_edit { background: #9e9e9e; color: #fff; }
  .badge.version_snapshot { background: #9c27b0; color: #fff; }

  .diff {
    white-space: pre-wrap;
    font-family: monospace;
    font-size: 12px;
    background: var(--vscode-editorWidget-background);
    padding: 6px;
    margin-top: 6px;
    display: none;
  }
  </style>
  </head>

  <body>

  <h2>Generated Test Cases</h2>

  <div id="editorWrapper" style="position: relative;">
    <pre id="featureText" contenteditable="true">${escaped}</pre>
    <div id="historySection" style="display:none; margin-top:16px;">
    <h3>
      Edit History
      <button id="closeHistory" style="float:right;">Close</button>
    </h3>
    <div id="historyTimeline"></div>
    </div>
    <div class="search-popup" id="searchPopup">
      <input id="searchBox" placeholder="🔎 Search Scenarios..." />
      <span class="match-count" id="matchCount">No Results</span>
      <button id="prevMatch" title="Previous match (Shift + Enter)">↑</button>
      <button id="nextMatch" title="Next match (Enter)">↓</button>
      <button id="closeSearch" title="Close search (Esc)">✖</button>
    </div>
  </div>



  <button id="generateBddTop" class="top-right-btn">⚙ Generate BDD</button>

  <div class="button-row">
    <div class="left-buttons">
      <button id="runTests">▶ Run Tests</button>
    </div>

    <div class="right-buttons">
    <button id="viewHistory" disabled>History</button>
    <button id="saveFeature">Save</button>
    <button id="saveVersion">Save Version</button>
    </div>
  </div>

  <div id="output"></div>

  <script>
  const vscode = acquireVsCodeApi();
  const featureTextEl = document.getElementById('featureText');
  const outputEl = document.getElementById('output');

  /* ---------- SEARCH ENGINE ---------- */
  let searchActive = false;
  let matches = [];
  let activeIndex = 0;
  let originalTextCache = featureTextEl.innerText;

  const popup = document.getElementById('searchPopup');
  const searchBox = document.getElementById('searchBox');
  const matchCountEl = document.getElementById('matchCount');

  function escapeHtml(text) {
    return text.replace(/</g,"&lt;").replace(/>/g,"&gt;");
  }

  function highlightKeywords(text) {
    return text.replace(/(Feature:|Scenario:|Given |When |Then |And )/g,
      '<span class="keyword">$1</span>');
  }

  /* REINITIALIZE SEARCH STATE */
  function activateSearch() {
    matches = [];
    activeIndex = -1;
    highlightMatches(searchBox.value.trim());
  }

  function highlightMatches(query) {
    matches = [];
    activeIndex = 0;

    if (!query) {
      featureTextEl.innerHTML = highlightKeywords(escapeHtml(originalTextCache));
      matchCountEl.textContent = "No Results"
      return;
    }

    const regex = new RegExp(query.replace(/[.*+?^\${}()|[\]\\]/g,'\\\\$&'), 'gi');
    let idx = 0;

    const html = escapeHtml(originalTextCache).replace(regex, m => {
      const cls = idx === 0 ? 'search-match active' : 'search-match';
      matches.push(idx++);
      return '<span class="'+cls+'">'+m+'</span>';
    });

    featureTextEl.innerHTML = highlightKeywords(html);
    updateCounter();
    scrollToActive();
  }

  function updateCounter() {
    matchCountEl.textContent = matches.length
      ? (activeIndex + 1) + " / " + matches.length
      : "No Results";
  }

  function scrollToActive() {
    const el = featureTextEl.querySelector('.search-match.active');
    if (el) el.scrollIntoView({ block: 'center' });
  }

  function move(delta) {
    if (!matches.length) return;
    const all = featureTextEl.querySelectorAll('.search-match');
    all[activeIndex].classList.remove('active');
    activeIndex = (activeIndex + delta + matches.length) % matches.length;
    all[activeIndex].classList.add('active');
    updateCounter();
    scrollToActive();
  }

  /* ❌ CLOSE SEARCH */
  function closeSearch() {
    popup.style.display = 'none';
    featureTextEl.contentEditable = "true";
    matches = [];
    activeIndex = -1;
    featureTextEl.innerHTML = highlightKeywords(
      escapeHtml(originalTextCache)
    );
  }

  /* Ctrl+F */
  window.addEventListener('keydown', e => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'f') {
      e.preventDefault();
      popup.style.display = 'flex';
      searchActive = true;
      featureTextEl.contentEditable = "false";
      searchBox.focus();
      activateSearch();
    }
      
    if (e.key === 'Escape' && popup.style.display === 'flex') {
      closeSearch();
    }

    if (popup.style.display === 'flex' && e.key === 'Enter') {
      e.preventDefault();
      move(e.shiftKey ? -1 : 1);     // 🔥 SINGLE MOVE
    }
  });

  searchBox.addEventListener('input', e => highlightMatches(e.target.value));
  document.getElementById('nextMatch').onclick = () => move(1);
  document.getElementById('prevMatch').onclick = () => move(-1);
  document.getElementById('closeSearch').onclick = closeSearch;

  /* ---------- EXISTING LOGIC (UNCHANGED) ---------- */
  const historySection = document.getElementById('historySection');
  const historyTimeline = document.getElementById('historyTimeline');

  document.getElementById('closeHistory').onclick = () => {
    historySection.style.display = 'none';
  };

  function renderHistory(entries) {
    const section = document.getElementById('historySection');
    const timeline = document.getElementById('historyTimeline');

    if (!entries || entries.length === 0) {
      timeline.innerHTML = "<p>No history available</p>";
      section.style.display = "block";
      return;
    }

    let html = "";

    for (let i = 0; i < entries.length; i++) {
      const e = entries[i];

      html +=
        '<div class="history-entry">' +
          '<div class="history-meta">' +
            '<span class="badge ' + e.source + '">' + e.source + '</span>' +
            new Date(e.timestamp).toLocaleString() +
          '</div>' +

          '<button onclick="toggleDiff(' + i + ')">Show Diff</button> ' +
          '<button onclick="restoreVersion(' + i + ')">Restore</button>' +

          '<div id="diff-' + i + '" class="diff">' +
            escapeHtml(e.diffSummary || "No diff available") +
          '</div>' +
        '</div>';
    }

    timeline.innerHTML = html;
    section.style.display = "block";
  }
  function toggleDiff(index) {
    const el = document.getElementById("diff-" + index);
    if (!el) return;

    el.style.display = el.style.display === "none" ? "block" : "none";
  }
  function restoreVersion(index) {
    vscode.postMessage({
      type: "restoreHistory",
      index: index
    });
  }

  featureTextEl.addEventListener('input', () => {
    if (searchActive) return;
    originalTextCache = featureTextEl.innerText;
    vscode.postMessage({ type: 'updateText', text: featureTextEl.innerText });
  });

  document.getElementById('runTests').onclick = () =>
    vscode.postMessage({ type: 'run' });

  document.getElementById('saveFeature').onclick = () =>
    vscode.postMessage({ type: 'save' });

  document.getElementById('saveVersion').onclick = () =>
    vscode.postMessage({ type: 'saveVersion' });

  document.getElementById('generateBddTop').onclick = () =>
    vscode.postMessage({ type: 'generateBDD' });

  document.getElementById('viewHistory').onclick = () =>
    vscode.postMessage({ type: 'viewHistory' });

  window.addEventListener('message', event => {
    const message = event.data;
    if (message.type === 'enableHistory') {
      document.getElementById('viewHistory').disabled = !message.enabled;
    }
    if (message.type === 'historyData') {
      renderHistory(message.entries);
    }
    if (message.type === 'setFeatureText') {
        featureTextEl.innerText = message.text;
      }
    if (message.type === 'output') {
        const iframeHtml = '<iframe id="reportFrame" style="width:100%; height:100%; border:none;"></iframe>';
        outputEl.innerHTML = iframeHtml;

        const iframe = document.getElementById('reportFrame');

        // Minimal CSS for iframe to normalize base styles without overriding report theme
        const forcedCss =
          '<style>' +
          'html, body { margin: 0; padding: 0; }' +
          '</style>';


        const out = (message.output || '').toString().trim();

        try {
          // If output looks like a URL (starts with http/https), load it by src
          if (/^https?:\\/\\//i.test(out)) {
            // NOTE: cross-origin pages cannot be styled from the parent. If the server returns a URL,
            // you cannot inject CSS unless the page is same-origin or the server itself includes the CSS.
            iframe.src = out;
          } else {
            // Insert style into the HTML string itself so it's present from first paint.
            let modified = out;
            if (/<\\/head\\s*>/i.test(modified)) {
              modified = modified.replace(/<\\/head\\s*>/i, forcedCss + '</head>');
            } else if (/^\\s*<!DOCTYPE/i.test(modified) || /^\\s*<html/i.test(modified)) {
              // Page has html but no head close — try to inject head
              modified = modified.replace(/<html[^>]*>/i, (m) => m + '<head>' + forcedCss + '</head>');
            } else {
              // Fallback: just prepend a head with style
              modified = '<head>' + forcedCss + '</head>' + modified;
            }

            // Finally set srcdoc (this will render the modified HTML including the forced CSS)
            iframe.srcdoc = modified;
          }
        } catch (err) {
          // Fallback: set srcdoc unmodified and try a late injection (may fail if cross-origin)
          console.error('iframe injection error', err);
          iframe.srcdoc = out;
          iframe.onload = () => {
            try {
              const iframeDoc = iframe.contentDocument || iframe.contentWindow.document;
              if (iframeDoc && iframeDoc.head) {
                const style = iframeDoc.createElement('style');
                style.innerHTML = 'html, body { margin: 0; padding: 0; }';
                iframeDoc.head.appendChild(style);
              }
            } catch (e) {
              console.error('late iframe style injection failed', e);
            }
          };
        }
      }
  });
  </script>
  </body>
  </html>`;
    }
  }



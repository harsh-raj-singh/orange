(function () {
  if (window.__orangeVoiceWidgetLoaded) return;
  window.__orangeVoiceWidgetLoaded = true;

  var currentScript =
    document.currentScript ||
    Array.prototype.slice
      .call(document.scripts)
      .reverse()
      .find(function (script) {
        return script.src && (script.src.indexOf("/orange-voice-widget.js") !== -1 || script.src.indexOf("/widget.js") !== -1);
      });

  var scriptUrl = currentScript && currentScript.src ? new URL(currentScript.src) : new URL(window.location.href);
  var apiBase = ((currentScript && currentScript.dataset.apiBase) || scriptUrl.origin).replace(/\/$/, "");
  var siteId = (currentScript && currentScript.dataset.siteId) || "orange-site";
  var assistantName = (currentScript && currentScript.dataset.assistantName) || "Orange Voice";
  var ctaLabel = (currentScript && currentScript.dataset.ctaLabel) || "Ask Orange";
  var maxRecordMs = Number((currentScript && currentScript.dataset.maxRecordMs) || 12000);
  var recorder = null;
  var stream = null;
  var chunks = [];
  var recordTimer = null;
  var activePlayer = null;
  var activeAudioUrl = null;

  function uuid() {
    if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
    return "orange_voice_" + Math.random().toString(36).slice(2) + Date.now().toString(36);
  }

  var sessionKey = "orange-voice:session:" + siteId;
  var sessionId = readStorage(sessionKey) || uuid();
  writeStorage(sessionKey, sessionId);

  var state = {
    open: false,
    busy: false,
    recording: false,
    speaking: false,
    status: "idle",
    message: "Press the mic or type a question about this page.",
    transcript: "",
    reply: "",
    draft: "",
    cursor: {
      x: Math.round(window.innerWidth / 2),
      y: Math.round(window.innerHeight / 2),
      t: Date.now(),
    },
  };

  var host = document.createElement("div");
  host.id = "orange-voice-widget-root";
  host.setAttribute("data-saarthi-private", "true");
  host.setAttribute("data-orange-voice-private", "true");
  var shadow = host.attachShadow({ mode: "open" });
  document.documentElement.appendChild(host);

  var css = document.createElement("style");
  css.textContent = [
    ":host{all:initial;position:fixed;z-index:2147483647;font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;color:#17221c}",
    "*{box-sizing:border-box}",
    ".wrap{position:fixed;right:22px;bottom:22px;display:flex;flex-direction:column;align-items:flex-end;gap:12px}",
    ".cursor{position:fixed;left:0;top:0;width:34px;height:34px;margin:-17px 0 0 -17px;border:2px solid rgba(249,115,22,.9);border-radius:999px;box-shadow:0 0 0 9px rgba(249,115,22,.18);pointer-events:none;opacity:0;transform:translate3d(var(--x),var(--y),0);transition:opacity .2s ease}",
    ".cursor.on{opacity:1}",
    ".panel{width:min(380px,calc(100vw - 32px));border:1px solid rgba(24,32,25,.14);border-radius:16px;background:rgba(255,250,242,.97);box-shadow:0 24px 80px rgba(0,0,0,.28);backdrop-filter:blur(18px);overflow:hidden;transform-origin:bottom right;animation:orange-voice-in .22s ease}",
    "@keyframes orange-voice-in{from{opacity:0;transform:translateY(10px) scale(.97)}to{opacity:1;transform:translateY(0) scale(1)}}",
    ".top{display:flex;align-items:center;gap:12px;padding:16px;border-bottom:1px solid rgba(24,32,25,.1);background:linear-gradient(135deg,rgba(255,247,237,.98),rgba(240,253,244,.92))}",
    ".mark{display:grid;place-items:center;width:42px;height:42px;border-radius:12px;background:#17221c;color:#ffb36b;font-weight:900;box-shadow:inset 0 -12px 24px rgba(249,115,22,.18)}",
    ".title{font-size:15px;font-weight:900;letter-spacing:0}.sub{font-size:12px;color:#5c6a60;margin-top:2px;line-height:1.35}",
    ".body{padding:16px;display:grid;gap:12px}",
    "button{font:800 14px/1 inherit;border:0;cursor:pointer;letter-spacing:0}",
    ".mic{display:grid;place-items:center;width:86px;height:86px;margin:2px auto;border-radius:999px;background:#17221c;color:#fff;box-shadow:0 18px 46px rgba(23,34,28,.24)}",
    ".mic:disabled{cursor:not-allowed;opacity:.58}.mic.recording{background:#c2410c;box-shadow:0 0 0 10px rgba(194,65,12,.16),0 18px 46px rgba(194,65,12,.2)}",
    ".mic svg{width:32px;height:32px}",
    ".actions{display:flex;gap:10px}.actions>*{flex:1;min-width:0}",
    ".secondary{height:42px;border-radius:10px;padding:0 13px;background:#fff3e7;color:#9a3f12;border:1px solid rgba(249,115,22,.22)}",
    ".secondary.stop{background:#fff1f2;color:#9f1239;border-color:rgba(225,29,72,.18)}",
    ".textAsk{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:8px}",
    ".textAsk input{min-width:0;height:42px;border-radius:10px;border:1px solid rgba(24,32,25,.14);background:#fff;padding:0 11px;color:#17221c;font:600 13px/1.2 inherit;outline:none}",
    ".textAsk input:focus{border-color:#f97316;box-shadow:0 0 0 3px rgba(249,115,22,.14)}",
    ".textAsk button{height:42px;border-radius:10px;background:#17221c;color:#fff;padding:0 13px}",
    ".textAsk button:disabled{cursor:not-allowed;opacity:.56}",
    ".note{padding:11px 12px;border-radius:12px;background:#fffaf2;color:#3b463d;font-size:13px;line-height:1.45;border:1px solid rgba(24,32,25,.1)}",
    ".note.good{background:#f0fdf4;color:#14532d;border-color:rgba(22,163,74,.18)}",
    ".note.warn{background:#fff7ed;color:#7c2d12;border-color:rgba(249,115,22,.22)}",
    ".pulse{display:inline-flex;width:7px;height:7px;border-radius:999px;background:#22c55e;margin-right:7px;box-shadow:0 0 0 5px rgba(34,197,94,.13);vertical-align:middle}",
    ".pulse.recording{background:#f97316;box-shadow:0 0 0 5px rgba(249,115,22,.15)}",
    ".fab{display:flex;align-items:center;justify-content:center;gap:10px;height:58px;border-radius:999px;padding:0 18px 0 13px;background:#f97316;color:#fff;box-shadow:0 18px 48px rgba(249,115,22,.34);border:1px solid rgba(255,255,255,.18)}",
    ".badge{display:grid;place-items:center;width:36px;height:36px;border-radius:999px;background:#17221c;color:#ffb36b;font-weight:900}",
    ".fabText{font-size:14px;font-weight:900}.hidden{display:none!important}",
    ".close{margin-left:auto;width:32px;height:32px;border-radius:10px;background:rgba(255,255,255,.72);color:#17221c}",
    ".mini{font-size:11px;color:#6b7280;line-height:1.35}.mono{font-family:'SFMono-Regular',Consolas,monospace}",
    ".label{font-size:11px;font-weight:900;text-transform:uppercase;color:#6b7280;letter-spacing:.12em;margin-bottom:6px}",
  ].join("");

  var root = document.createElement("div");
  shadow.appendChild(css);
  shadow.appendChild(root);

  function micSvg() {
    return '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M12 14a3 3 0 0 0 3-3V6a3 3 0 1 0-6 0v5a3 3 0 0 0 3 3Z" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><path d="M19 11a7 7 0 0 1-14 0M12 18v3M8 21h8" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>';
  }

  function render() {
    root.innerHTML =
      '<div class="cursor ' +
      (state.open ? "on" : "") +
      '" style="--x:' +
      state.cursor.x +
      "px;--y:" +
      state.cursor.y +
      'px"></div>' +
      '<div class="wrap">' +
      '<section class="panel ' +
      (state.open ? "" : "hidden") +
      '" aria-live="polite">' +
      '<div class="top"><div class="mark">O</div><div><div class="title">' +
      escapeHtml(assistantName) +
      '</div><div class="sub"><span class="pulse ' +
      (state.recording ? "recording" : "") +
      '"></span>' +
      (state.recording ? "Listening on this page" : "Voice guide for Orange") +
      '</div></div><button class="close" type="button" data-action="close" aria-label="Close Orange Voice">x</button></div>' +
      '<div class="body">' +
      '<button class="mic ' +
      (state.recording ? "recording" : "") +
      '" type="button" data-action="' +
      (state.recording ? "stop" : "record") +
      '" ' +
      (state.busy && !state.recording ? "disabled" : "") +
      ' aria-label="' +
      (state.recording ? "Stop recording" : "Ask Orange") +
      '">' +
      micSvg() +
      "</button>" +
      '<div class="actions"><button class="secondary ' +
      (state.recording ? "stop" : "") +
      '" type="button" data-action="' +
      (state.recording ? "stop" : "record") +
      '" ' +
      (state.busy && !state.recording ? "disabled" : "") +
      ">" +
      (state.recording ? "Stop" : state.busy ? "Thinking..." : "Hold a voice turn") +
      '</button><button class="secondary stop" type="button" data-action="stop-speech" ' +
      (state.speaking ? "" : "disabled") +
      ' aria-label="Stop Orange speaking">Stop voice</button></div>' +
      '<form class="textAsk" data-action="text-question">' +
      '<input data-field="draft" type="text" autocomplete="off" placeholder="Type a question..." value="' +
      escapeHtml(state.draft) +
      '" ' +
      (state.busy || state.recording ? "disabled" : "") +
      " />" +
      '<button type="submit" ' +
      (state.busy || state.recording ? "disabled" : "") +
      ">Ask</button>" +
      "</form>" +
      '<div class="note ' +
      (state.status === "ready" ? "good" : state.status === "error" ? "warn" : "") +
      '">' +
      escapeHtml(state.message) +
      "</div>" +
      (state.transcript ? '<div class="note"><div class="label">You said</div>' + escapeHtml(state.transcript) + "</div>" : "") +
      (state.reply ? '<div class="note good"><div class="label">Orange said</div>' + escapeHtml(state.reply) + "</div>" : "") +
      '<div class="mini">Session <span class="mono">' +
      escapeHtml(sessionId.slice(0, 8)) +
      '</span>. Hover over anything, then ask what it means or what to do next.</div>' +
      "</div></section>" +
      '<button class="fab" type="button" data-action="toggle" aria-label="Open Orange Voice"><span class="badge">O</span><span class="fabText">' +
      escapeHtml(ctaLabel) +
      "</span></button>" +
      "</div>";
  }

  function escapeHtml(value) {
    return String(value || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function readStorage(key) {
    try {
      return window.localStorage ? localStorage.getItem(key) : null;
    } catch {
      return null;
    }
  }

  function writeStorage(key, value) {
    try {
      if (window.localStorage) localStorage.setItem(key, value);
    } catch {
      // Embedded contexts may block storage; a one-tab session still works.
    }
  }

  function cssEscape(value) {
    if (window.CSS && CSS.escape) return CSS.escape(value);
    return String(value).replace(/[^a-zA-Z0-9_-]/g, "\\$&");
  }

  function setState(next) {
    Object.assign(state, next);
    render();
  }

  function updateCursor(event) {
    var path = event.composedPath ? event.composedPath() : [];
    if (path.indexOf(host) !== -1) return;

    state.cursor = {
      x: Math.max(0, Math.min(window.innerWidth, Math.round(event.clientX))),
      y: Math.max(0, Math.min(window.innerHeight, Math.round(event.clientY))),
      t: Date.now(),
    };
    var cursor = shadow.querySelector(".cursor");
    if (cursor) {
      cursor.style.setProperty("--x", state.cursor.x + "px");
      cursor.style.setProperty("--y", state.cursor.y + "px");
    }
  }

  function safeUrl(value) {
    if (!value) return null;
    try {
      var url = new URL(value, window.location.href);
      url.search = "";
      url.hash = "";
      return url.toString();
    } catch {
      return String(value).split("?")[0].split("#")[0].slice(0, 220);
    }
  }

  function pageUrl() {
    return safeUrl(window.location.href);
  }

  function buildSelector(el) {
    if (!el || !el.tagName) return null;
    if (el.id) return "#" + cssEscape(el.id);
    var parts = [];
    var node = el;
    while (node && node.nodeType === 1 && parts.length < 4 && node !== document.documentElement) {
      var part = node.tagName.toLowerCase();
      var testId = node.getAttribute("data-testid") || node.getAttribute("data-test");
      if (testId) part += '[data-testid="' + testId.replace(/"/g, '\\"') + '"]';
      parts.unshift(part);
      node = node.parentElement;
    }
    return parts.join(" > ");
  }

  function isElementVisible(el) {
    if (!el || !el.getBoundingClientRect) return false;
    if (el.closest && el.closest("[data-saarthi-private],[data-orange-voice-private]")) return false;
    var style = window.getComputedStyle ? window.getComputedStyle(el) : null;
    if (style && (style.visibility === "hidden" || style.display === "none" || Number(style.opacity) === 0)) return false;
    var rect = el.getBoundingClientRect();
    return rect.width > 1 && rect.height > 1 && rect.bottom >= 0 && rect.right >= 0 && rect.top <= window.innerHeight && rect.left <= window.innerWidth;
  }

  function visibleHeadings() {
    return Array.prototype.slice
      .call(document.querySelectorAll("h1,h2,h3,h4,[role='heading']"))
      .filter(isElementVisible)
      .map(function (node) {
        return (node.innerText || node.textContent || "").replace(/\s+/g, " ").trim();
      })
      .filter(Boolean)
      .slice(0, 18);
  }

  function visiblePageText() {
    if (!document.body || !document.createTreeWalker) return "";
    var lines = [];
    var seen = {};
    var walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, {
      acceptNode: function (node) {
        var text = (node.nodeValue || "").replace(/\s+/g, " ").trim();
        if (text.length < 2) return NodeFilter.FILTER_REJECT;
        var parent = node.parentElement;
        if (!parent) return NodeFilter.FILTER_REJECT;
        if (parent.closest("[data-saarthi-private],[data-orange-voice-private],script,style,noscript,svg,canvas")) {
          return NodeFilter.FILTER_REJECT;
        }
        if (["INPUT", "TEXTAREA", "SELECT", "OPTION"].indexOf(parent.tagName) !== -1) {
          return NodeFilter.FILTER_REJECT;
        }
        if (!isElementVisible(parent)) return NodeFilter.FILTER_REJECT;

        var range = document.createRange();
        range.selectNodeContents(node);
        var rect = range.getBoundingClientRect();
        if (range.detach) {
          range.detach();
        }
        if (!rect || rect.width < 1 || rect.height < 1) return NodeFilter.FILTER_REJECT;
        if (rect.bottom < 0 || rect.right < 0 || rect.top > window.innerHeight || rect.left > window.innerWidth) {
          return NodeFilter.FILTER_REJECT;
        }

        return NodeFilter.FILTER_ACCEPT;
      },
    });

    while (walker.nextNode() && lines.length < 90) {
      var line = (walker.currentNode.nodeValue || "").replace(/\s+/g, " ").trim().slice(0, 220);
      if (line && !seen[line]) {
        seen[line] = true;
        lines.push(line);
      }
    }

    return lines.join("\n").slice(0, 5200);
  }

  function describeElement(el) {
    if (!el) return {};
    if (el.closest && el.closest("[data-saarthi-private],[data-orange-voice-private]")) {
      return {
        private: true,
        tagName: el.tagName ? el.tagName.toLowerCase() : undefined,
      };
    }

    var rect = el.getBoundingClientRect ? el.getBoundingClientRect() : null;
    var labelText = "";
    var id = el.getAttribute && el.getAttribute("id");
    if (id) {
      var label = document.querySelector('label[for="' + cssEscape(id) + '"]');
      labelText = label ? label.innerText : "";
    }
    var labelledBy = el.getAttribute && el.getAttribute("aria-labelledby");
    if (labelledBy) {
      labelText = labelledBy
        .split(/\s+/)
        .map(function (item) {
          var node = document.getElementById(item);
          return node ? node.innerText : "";
        })
        .join(" ");
    }

    var text = labelText || el.innerText || el.textContent || "";
    text = text.replace(/\s+/g, " ").trim().slice(0, 700);

    return {
      tagName: el.tagName ? el.tagName.toLowerCase() : undefined,
      type: el.getAttribute && (el.getAttribute("type") || null),
      role: el.getAttribute && (el.getAttribute("role") || null),
      id: id || null,
      className: typeof el.className === "string" ? el.className.slice(0, 180) : null,
      name: el.getAttribute && (el.getAttribute("name") || null),
      innerText: text || null,
      ariaLabel: el.getAttribute && (el.getAttribute("aria-label") || null),
      title: el.getAttribute && (el.getAttribute("title") || null),
      placeholder: el.getAttribute && (el.getAttribute("placeholder") || null),
      href: el.getAttribute && safeUrl(el.getAttribute("href")),
      value: null,
      selector: buildSelector(el),
      rect: rect
        ? {
            x: Math.round(rect.x),
            y: Math.round(rect.y),
            width: Math.round(rect.width),
            height: Math.round(rect.height),
          }
        : null,
    };
  }

  function pageContext() {
    var cursor = state.cursor;
    var target = document.elementFromPoint(cursor.x, cursor.y);
    return {
      siteId: siteId,
      sessionId: sessionId,
      capturedAt: new Date().toISOString(),
      page: {
        url: pageUrl(),
        title: document.title,
        headings: visibleHeadings(),
        visibleText: visiblePageText(),
        viewport: { width: window.innerWidth, height: window.innerHeight },
        scroll: { x: window.scrollX, y: window.scrollY },
        cursor: { x: cursor.x, y: cursor.y },
      },
      element: describeElement(target),
      visibleControls: visibleControls(),
    };
  }

  function visibleControls() {
    var selector = [
      "a[href]",
      "button",
      "input",
      "select",
      "textarea",
      "summary",
      "[role='button']",
      "[role='link']",
      "[role='menuitem']",
      "[tabindex]:not([tabindex='-1'])",
    ].join(",");
    var nodes = Array.prototype.slice.call(document.querySelectorAll(selector));
    var controls = [];

    for (var i = 0; i < nodes.length && controls.length < 24; i += 1) {
      var node = nodes[i];
      if (!node || node === host || (node.closest && node.closest("[data-saarthi-private],[data-orange-voice-private]"))) continue;
      if (!isElementVisible(node)) continue;

      var summary = describeElement(node);
      if (summary.innerText || summary.ariaLabel || summary.placeholder || summary.title || summary.value) {
        controls.push(summary);
      }
    }

    return controls;
  }

  function filenameForMime(type) {
    if (/mp4|m4a/i.test(type)) return "orange-voice.m4a";
    if (/wav/i.test(type)) return "orange-voice.wav";
    if (/ogg/i.test(type)) return "orange-voice.ogg";
    return "orange-voice.webm";
  }

  function chooseMimeType() {
    var candidates = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/wav"];
    for (var i = 0; i < candidates.length; i += 1) {
      if (window.MediaRecorder && MediaRecorder.isTypeSupported(candidates[i])) {
        return candidates[i];
      }
    }
    return "";
  }

  function stopTracks() {
    if (stream) {
      stream.getTracks().forEach(function (track) {
        track.stop();
      });
    }
    stream = null;
  }

  function clearActiveAudio() {
    if (activePlayer) {
      activePlayer.onended = null;
      activePlayer.onerror = null;
      activePlayer.pause();
      activePlayer.currentTime = 0;
    }
    if (activeAudioUrl) {
      URL.revokeObjectURL(activeAudioUrl);
    }
    activePlayer = null;
    activeAudioUrl = null;
  }

  function stopSpeech(silent) {
    var wasSpeaking = state.speaking || activePlayer;
    clearActiveAudio();
    if (silent) {
      state.speaking = false;
      return;
    }
    setState({
      speaking: false,
      status: wasSpeaking ? "ready" : state.status,
      message: wasSpeaking ? "Orange stopped speaking." : "Orange is not speaking right now.",
    });
  }

  function microphoneErrorMessage(error) {
    var name = error && error.name ? error.name : "";
    if (name === "NotAllowedError" || name === "PermissionDeniedError") {
      return "Microphone access is blocked for this browser. Allow microphone access in the address bar, or type your question below.";
    }
    if (name === "NotFoundError" || name === "DevicesNotFoundError") {
      return "I could not find a microphone. You can still type your question below.";
    }
    return error && error.message
      ? error.message + " You can still type your question below."
      : "Microphone permission was not granted. You can still type your question below.";
  }

  function startRecording() {
    stopSpeech(true);

    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia || !window.MediaRecorder) {
      setState({
        status: "error",
        message: "This browser does not support in-page voice recording. Type your question below instead.",
      });
      return;
    }

    setState({
      open: true,
      busy: false,
      recording: true,
      status: "recording",
      message: "Listening. Ask what Orange means, what this section does, or what to click next.",
      transcript: "",
      reply: "",
    });

    navigator.mediaDevices
      .getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      })
      .then(function (mediaStream) {
        stream = mediaStream;
        chunks = [];
        var mimeType = chooseMimeType();
        recorder = new MediaRecorder(stream, mimeType ? { mimeType: mimeType } : undefined);
        recorder.ondataavailable = function (event) {
          if (event.data && event.data.size > 0) chunks.push(event.data);
        };
        recorder.onstop = finishRecording;
        recorder.start();
        recordTimer = window.setTimeout(stopRecording, Math.max(4000, maxRecordMs));
      })
      .catch(function (error) {
        stopTracks();
        setState({
          busy: false,
          recording: false,
          status: "error",
          message: microphoneErrorMessage(error),
        });
      });
  }

  function stopRecording() {
    if (recordTimer) window.clearTimeout(recordTimer);
    recordTimer = null;
    if (recorder && recorder.state !== "inactive") {
      recorder.stop();
    }
  }

  function finishRecording() {
    stopTracks();
    setState({
      busy: true,
      recording: false,
      status: "processing",
      message: "Transcribing and thinking...",
    });

    var type = chunks[0] && chunks[0].type ? chunks[0].type : "audio/webm";
    var audioBlob = new Blob(chunks, { type: type });
    chunks = [];

    if (!audioBlob.size) {
      setState({
        busy: false,
        status: "error",
        message: "I could not capture audio. Please try once more.",
      });
      return;
    }

    var context;
    try {
      context = pageContext();
    } catch {
      setState({
        busy: false,
        status: "error",
        message: "I could not read the page context. Please move your cursor and try again.",
      });
      return;
    }

    var form = new FormData();
    form.append("audio", audioBlob, filenameForMime(type));
    form.append("context", JSON.stringify(context));

    var controller = new AbortController();
    var timeout = window.setTimeout(function () {
      controller.abort();
    }, 120000);

    fetch(apiBase + "/api/voice/turn", {
      method: "POST",
      headers: {
        "X-Saarthi-Session": sessionId,
        "X-Orange-Voice-Session": sessionId,
      },
      body: form,
      signal: controller.signal,
    })
      .then(function (res) {
        return res.json().then(function (data) {
          if (!res.ok || data.ok === false) throw new Error(data.error || "Voice turn failed.");
          return data;
        });
      })
      .then(function (data) {
        setState({
          busy: false,
          status: "ready",
          message: "Orange answered out loud.",
          transcript: data.transcript || "",
          reply: data.reply || "",
        });
        playAudio(data.audio);
      })
      .catch(function (error) {
        setState({
          busy: false,
          status: "error",
          message:
            error && error.name === "AbortError"
              ? "That took too long. Please try a shorter question."
              : error.message || "Orange Voice could not process that voice turn.",
        });
      })
      .finally(function () {
        window.clearTimeout(timeout);
      });
  }

  function askWithText() {
    var question = String(state.draft || "").trim();
    if (!question || state.busy || state.recording) {
      if (!question) {
        setState({
          status: "error",
          message: "Type a question first, then press Ask.",
        });
      }
      return;
    }
    stopSpeech(true);

    var context;
    try {
      context = pageContext();
    } catch {
      setState({
        busy: false,
        status: "error",
        message: "I could not read the page context. Please move your cursor and try again.",
      });
      return;
    }

    setState({
      busy: true,
      recording: false,
      status: "processing",
      message: "Reading this page and thinking...",
      transcript: question,
      reply: "",
      draft: "",
    });

    var controller = new AbortController();
    var timeout = window.setTimeout(function () {
      controller.abort();
    }, 120000);

    fetch(apiBase + "/api/voice/turn", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Saarthi-Session": sessionId,
        "X-Orange-Voice-Session": sessionId,
      },
      body: JSON.stringify({
        question: question,
        context: context,
      }),
      signal: controller.signal,
    })
      .then(function (res) {
        return res.json().then(function (data) {
          if (!res.ok || data.ok === false) throw new Error(data.error || "Question failed.");
          return data;
        });
      })
      .then(function (data) {
        setState({
          busy: false,
          status: "ready",
          message: "Orange answered. You can keep typing or allow microphone access.",
          transcript: data.transcript || question,
          reply: data.reply || "",
        });
        playAudio(data.audio);
      })
      .catch(function (error) {
        setState({
          busy: false,
          status: "error",
          message:
            error && error.name === "AbortError"
              ? "That took too long. Please try a shorter question."
              : error.message || "Orange Voice could not answer that question.",
          draft: question,
        });
      })
      .finally(function () {
        window.clearTimeout(timeout);
      });
  }

  function playAudio(audio) {
    if (!audio || !audio.base64) return;
    stopSpeech(true);
    var byteString = atob(audio.base64);
    var bytes = new Uint8Array(byteString.length);
    for (var i = 0; i < byteString.length; i += 1) {
      bytes[i] = byteString.charCodeAt(i);
    }
    var blob = new Blob([bytes], { type: audio.contentType || "audio/mpeg" });
    var url = URL.createObjectURL(blob);
    var player = new Audio(url);
    activePlayer = player;
    activeAudioUrl = url;
    player.onended = function () {
      clearActiveAudio();
      setState({
        speaking: false,
        status: "ready",
        message: "Orange finished speaking.",
      });
    };
    player.onerror = function () {
      clearActiveAudio();
      setState({
        speaking: false,
        status: "error",
        message: "Orange has an answer, but the audio could not play.",
      });
    };
    player
      .play()
      .then(function () {
        setState({
          speaking: true,
          status: "ready",
          message: "Orange is speaking. Press Stop voice any time.",
        });
      })
      .catch(function () {
        clearActiveAudio();
        setState({
          speaking: false,
          status: "ready",
          message: "Orange has an answer, but the browser blocked autoplay. Press the mic again to continue.",
        });
      });
  }

  shadow.addEventListener("click", function (event) {
    var actionTarget = event.target && event.target.closest ? event.target.closest("[data-action]") : null;
    var action = actionTarget && actionTarget.getAttribute("data-action");
    if (action === "toggle") setState({ open: !state.open });
    if (action === "close") setState({ open: false });
    if (action === "record") startRecording();
    if (action === "stop") stopRecording();
    if (action === "stop-speech") stopSpeech(false);
  });

  shadow.addEventListener("input", function (event) {
    var target = event.target;
    if (target && target.getAttribute && target.getAttribute("data-field") === "draft") {
      state.draft = target.value;
    }
  });

  shadow.addEventListener("submit", function (event) {
    var target = event.target;
    if (target && target.getAttribute && target.getAttribute("data-action") === "text-question") {
      event.preventDefault();
      askWithText();
    }
  });

  window.addEventListener("pointermove", updateCursor, { passive: true });
  window.addEventListener("mousemove", updateCursor, { passive: true });
  window.addEventListener("beforeunload", function () {
    window.__orangeVoiceWidgetLoaded = false;
    stopRecording();
    stopTracks();
    stopSpeech(true);
  });

  render();
})();

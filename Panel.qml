import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Commons as Commons
import qs.Ui

// Omarchy Snap to Agent: a bar icon and a popup panel that sends what you are
// looking at, with context, to the default agent chosen in Omarchy.
//
// Everything that is not drawing lives in helper/snap.py (capture, context,
// secret masking, the agent adapters). This file starts it and shows the result.
// Nothing is sent until the preview has been confirmed with Send.
//
// Colours, fonts, radius and spacing come from qs.Commons (Color, Style), which
// the shell updates in place on a theme switch. Nothing here is hard-coded.
// Everything shown from a capture (titles, log lines, OCR text) is untrusted
// text, so every Text is Text.PlainText.
Panel {
  id: root
  moduleName: "io.github.petervinter.snap-to-agent"
  ipcTarget: "io.github.petervinter.snap-to-agent"
  manageIpc: false

  // ------------------------------------------------------------------ state

  property string phase: "idle"       // idle | capturing | composing | ready | sending | sent | copied
  property var snap: null             // { mode, capture, context } from the helper
  property var preview: null          // the helper's compose() record
  property string question: ""
  property string contextText: ""     // what the context box shows
  property bool contextEdited: false
  property bool contextOpen: false
  property var allow: []              // ids of masks the user undid
  property bool sendImage: true       // false = text only (masked), for screenshots that show secrets
  property var pickItems: []          // newest notifications, for the picker
  property int pickIndex: 0
  property string page: "menu"        // menu | history | settings
  property bool pageActive: false     // a page was asked for, so it shows even with a capture waiting
  property var historyItems: []
  property int historyIndex: 0
  property var cfg: null              // settings being edited
  property int cfgStamp: 0            // bumps when the text fields must be refilled
  property var hookStatus: ({})
  property string cfgPath: ""
  property string settingsNote: ""
  property bool hookConfirm: false
  property string errorCode: ""
  property string errorMessage: ""
  property real flashStamp: 0

  readonly property bool busy: phase === "capturing" || phase === "sending"
  readonly property bool hasPreview: snap !== null && preview !== null
  readonly property bool agentOk: hasPreview && preview.ok === true
  readonly property var target: hasPreview ? (preview.target || ({})) : ({})
  readonly property var findings: hasPreview ? (preview.findings || []) : []
  readonly property var maskedFindings: findings.filter(function(f) { return f.masked })
  readonly property bool canSend: phase === "ready" && agentOk && target.installed !== false
  readonly property bool hasImage: snap !== null && !!snap.capture
  readonly property var imageSecrets: hasPreview ? (preview.image_secrets || []) : []

  readonly property string view: errorCode !== "" ? "error"
    : phase === "capturing" ? "capturing"
    : phase === "picking" ? "pick"
    : phase === "sending" ? "sending"
    : phase === "sent" || phase === "copied" ? "done"
    : pageActive ? (page === "history" ? "history" : page === "settings" ? "settings" : "idle")
    : hasPreview ? (agentOk ? "ready" : "noagent")
    : "idle"

  readonly property string helperPath: Qt.resolvedUrl("helper/snap.py").toString().replace(/^file:\/\//, "")

  Commons.Translations { id: strings; directory: Qt.resolvedUrl("i18n") }

  // ------------------------------------------------------------------ theme

  readonly property color fg: Commons.Color.popups.text
  readonly property color dim: Qt.rgba(fg.r, fg.g, fg.b, 0.62)
  readonly property color faint: Qt.rgba(fg.r, fg.g, fg.b, 0.4)
  readonly property color accent: Commons.Color.accent
  readonly property color warn: Commons.Color.urgent
  readonly property string fontFamily: Style.font.family
  readonly property color barFg: bar ? bar.barForeground : Commons.Color.bar.text

  readonly property string glyphSend: String.fromCodePoint(0xF048A)      // send
  readonly property string glyphWarn: String.fromCodePoint(0xF0026)      // alert
  readonly property string glyphOk: String.fromCodePoint(0xF012C)        // check
  readonly property string glyphChevron: String.fromCodePoint(0xF0142)   // chevron-right

  // ------------------------------------------------------------ helper calls

  // What is sent as the question: typed text, else the translated default (the built-in
  // one only; a default from the settings file comes from the helper as it is).
  function finalQuestion() {
    if (question.trim() !== "") return question
    if (hasPreview && preview.default_source === "builtin") return strings.t("question.default." + snap.mode, "")
    return ""
  }

  function stateForHelper(final) {
    var s = { question: final ? finalQuestion() : question, mode: snap.mode, capture: snap.capture, context: snap.context, allow: allow,
              source: snap.source || null, ocr: snap.ocr || null, send_image: sendImage }
    if (contextEdited) s.context_text = contextText
    return s
  }

  function fail(code, message) {
    phase = "idle"
    errorCode = code
    errorMessage = message || ""
    if (code !== "cancelled" && !opened) open()
  }

  function clearError() { errorCode = ""; errorMessage = "" }

  function startCapture(mode, geometry) {
    if (busy) return
    clearError()
    pageActive = false
    if (opened) close()
    phase = "capturing"
    // Give the panel a moment to leave the screen before the capture.
    startTimer.mode = mode
    startTimer.geometry = geometry || ""
    startTimer.restart()
  }

  function showPage(name) {
    if (busy) return
    clearError()
    page = name
    pageActive = true
    hookConfirm = false
    settingsNote = ""
    if (name === "history") { historyIndex = 0; historyProc.running = true }
    if (name === "settings") settingsGetProc.running = true
    if (!opened) open()
    Qt.callLater(function() { if (panel.loadedContent) panel.loadedContent.forceActiveFocus() })
  }

  function sendAgain(id) {
    historyOpenProc.command = ["python3", "-I", root.helperPath, "history-open", String(id)]
    historyOpenProc.running = true
  }

  function removeHistory(id) {
    historyDelProc.command = ["python3", "-I", root.helperPath, "history-delete", String(id)]
    historyDelProc.running = true
  }

  function setCfg(path, value) {
    var c = JSON.parse(JSON.stringify(cfg))
    var node = c
    for (var i = 0; i < path.length - 1; i++) node = node[path[i]]
    node[path[path.length - 1]] = value
    cfg = c
    settingsNote = ""
  }

  function listFrom(text) {
    return String(text).split(",").map(function(x) { return x.trim() }).filter(function(x) { return x !== "" })
  }

  function saveSettings() {
    settingsSetProc.payload = JSON.stringify({ config: cfg })
    settingsSetProc.running = true
  }

  function setHook(on) {
    hookConfirm = false
    hookProc.command = on ? ["python3", "-I", root.helperPath, "install-hook", "--yes"]
                          : ["python3", "-I", root.helperPath, "uninstall-hook"]
    hookProc.running = true
  }

  Process {
    id: historyProc
    command: ["python3", "-I", root.helperPath, "history"]
    stdout: StdioCollector { id: historyOut }
    onExited: function(code) {
      var r = root.parse(historyOut.text)
      root.historyItems = r && r.ok ? r.items : []
      root.historyIndex = 0
    }
  }

  Process {
    id: historyOpenProc
    stdout: StdioCollector { id: historyOpenOut }
    onExited: function(code) {
      var r = root.parse(historyOpenOut.text)
      if (r && r.ok) root.applySnap(r)
      else { root.errorCode = "no-last"; root.errorMessage = "" }
    }
  }

  Process {
    id: historyDelProc
    stdout: StdioCollector { id: historyDelOut }
    onExited: function(code) { historyProc.running = true }
  }

  Process {
    id: settingsGetProc
    command: ["python3", "-I", root.helperPath, "settings-get"]
    stdout: StdioCollector { id: settingsGetOut }
    onExited: function(code) {
      var r = root.parse(settingsGetOut.text)
      if (r && r.ok) {
        root.cfg = r.config
        root.hookStatus = r.hook || ({})
        root.cfgPath = String(r.path || "")
        root.cfgStamp = root.cfgStamp + 1
      } else {
        root.settingsNote = "failed"
      }
    }
  }

  Process {
    id: settingsSetProc
    property string payload: ""
    command: ["python3", "-I", root.helperPath, "settings-set"]
    stdinEnabled: true
    stdout: StdioCollector { id: settingsSetOut }
    onStarted: write(payload + "\n")
    onExited: function(code) {
      var r = root.parse(settingsSetOut.text)
      if (r && r.ok) { root.cfg = r.config; root.cfgStamp = root.cfgStamp + 1; root.settingsNote = "saved" }
      else root.settingsNote = "failed"
    }
  }

  Process {
    id: settingsResetProc
    command: ["python3", "-I", root.helperPath, "settings-reset"]
    stdout: StdioCollector { id: settingsResetOut }
    onExited: function(code) {
      var r = root.parse(settingsResetOut.text)
      if (r && r.ok) { root.cfg = r.config; root.cfgStamp = root.cfgStamp + 1; root.settingsNote = "saved" }
    }
  }

  Process {
    id: hookProc
    stdout: StdioCollector { id: hookOut }
    onExited: function(code) {
      var r = root.parse(hookOut.text)
      root.settingsNote = r && r.ok ? "hook" : "failed"
      settingsGetProc.running = true
    }
  }

  function startPick() {
    if (busy) return
    clearError()
    pickItems = []
    pickIndex = 0
    phase = "picking"
    pickProc.running = true
    if (!opened) open()
  }

  function choose(index) {
    if (phase !== "picking") return
    phase = "capturing"
    capProc.command = ["python3", "-I", root.helperPath, "capture", "notification", "--index", String(index)]
    capProc.running = true
  }

  function setSendImage(value) {
    if (sendImage === value) return
    sendImage = value
    runCompose(false)
  }

  Process {
    id: pickProc
    command: ["python3", "-I", root.helperPath, "notifications"]
    stdout: StdioCollector { id: pickOut }
    onExited: function(code) {
      var r = root.parse(pickOut.text)
      if (r && r.ok && r.items && r.items.length > 0) {
        root.pickItems = r.items
        root.pickIndex = 0
        Qt.callLater(function() { if (panel.loadedContent) panel.loadedContent.forceActiveFocus() })
      } else {
        root.fail(r ? String(r.error || "no-notifications") : "helper", "")
      }
    }
  }

  Timer {
    id: startTimer
    property string mode: "region"
    property string geometry: ""
    interval: 320
    onTriggered: {
      var args = ["python3", "-I", root.helperPath, "capture", mode]
      if (geometry !== "") args = args.concat(["--geometry", geometry])
      capProc.command = args
      capProc.running = true
    }
  }

  function applySnap(data) {
    snap = { mode: data.mode, capture: data.capture || null, context: data.context, source: data.source || null,
             ocr: data.ocr || null }
    pageActive = false
    question = data.question ? String(data.question) : ""
    allow = []
    sendImage = true
    contextEdited = false
    contextText = ""
    preview = null
    phase = "composing"
    flashStamp = Date.now()
    runCompose(true)
    if (!opened) open()
  }

  function runCompose(resetContext) {
    if (!snap) return
    composeProc.resetContext = resetContext
    if (composeProc.running) { composeAgain = true; return }
    composeProc.payload = JSON.stringify(stateForHelper())
    composeProc.running = true
  }
  property bool composeAgain: false

  function send() {
    if (!canSend) return
    phase = "sending"
    sendProc.payload = JSON.stringify(stateForHelper(true))
    sendProc.running = true
  }

  function copy() {
    if (!hasPreview || phase !== "ready") return
    copyProc.payload = JSON.stringify(stateForHelper(true))
    copyProc.running = true
  }

  function undoMask(id) {
    if (allow.indexOf(id) >= 0) return
    allow = allow.concat([id])
    contextEdited = false   // an edited context keeps its placeholders, so start from the generated one
    runCompose(true)
  }

  function resend() {
    if (busy) return
    clearError()
    lastProc.running = true
  }

  function discard() {
    snap = null
    preview = null
    phase = "idle"
    clearError()
  }

  function openAgentSetup() {
    Quickshell.execDetached(["omarchy-menu", "summon", "setup.default.agent"])
    close()
  }

  function parse(text) {
    try { return JSON.parse(text) } catch (e) { return null }
  }

  Process {
    id: capProc
    stdout: StdioCollector { id: capOut }
    onExited: function(code) {
      var r = root.parse(capOut.text)
      if (r && r.ok) root.applySnap(r)
      else root.fail(r ? String(r.error || "generic") : "helper", r ? String(r.message || "") : "")
    }
  }

  Process {
    id: composeProc
    property string payload: ""
    property bool resetContext: false
    command: ["python3", "-I", root.helperPath, "compose"]
    stdinEnabled: true
    stdout: StdioCollector { id: composeOut }
    onStarted: write(payload + "\n")
    onExited: function(code) {
      var r = root.parse(composeOut.text)
      if (r && r.context !== undefined) {
        root.preview = r
        if (resetContext || root.contextText === "") root.contextText = String(r.context)
        if (root.phase === "composing") root.phase = "ready"
        Qt.callLater(function() { if (panel.loadedContent) panel.loadedContent.focusQuestion() })
      } else if (root.phase === "composing") {
        root.fail("helper", "")
      }
      if (root.composeAgain) { root.composeAgain = false; root.runCompose(false) }
    }
  }

  Process {
    id: sendProc
    property string payload: ""
    command: ["python3", "-I", root.helperPath, "send"]
    stdinEnabled: true
    stdout: StdioCollector { id: sendOut }
    onStarted: write(payload + "\n")
    onExited: function(code) {
      var r = root.parse(sendOut.text)
      if (r && r.ok) {
        root.phase = "sent"
        doneTimer.restart()
      } else {
        root.phase = "ready"
        root.errorCode = r ? String(r.error || "generic") : "helper"
        root.errorMessage = r ? String(r.message || r.problem || "") : ""
      }
    }
  }

  Process {
    id: copyProc
    property string payload: ""
    command: ["python3", "-I", root.helperPath, "copy"]
    stdinEnabled: true
    stdout: StdioCollector { id: copyOut }
    onStarted: write(payload + "\n")
    onExited: function(code) {
      var r = root.parse(copyOut.text)
      if (r && r.ok) {
        root.phase = "copied"
        doneTimer.restart()
      } else {
        root.errorCode = r ? String(r.error || "generic") : "helper"
        root.errorMessage = r ? String(r.message || "") : ""
      }
    }
  }

  Process {
    id: lastProc
    command: ["python3", "-I", root.helperPath, "last"]
    stdout: StdioCollector { id: lastOut }
    onExited: function(code) {
      var r = root.parse(lastOut.text)
      if (r && r.ok) root.applySnap(r)
      else root.fail(r ? String(r.error || "no-last") : "helper", "")
    }
  }

  // Confirmation stays on screen for a moment, then the panel leaves.
  Timer {
    id: doneTimer
    interval: 1400
    onTriggered: { root.close(); root.discard() }
  }

  Timer {
    id: recompose
    interval: 260
    onTriggered: root.runCompose(false)
  }

  // --------------------------------------------------------------- shell IPC

  ShellIpc {
    target: root.ipcTarget
    function open(): void { root.open() }
    function close(): void { root.close() }
    function toggle(): void { root.toggle() }
    function capture(mode: string): string {
      if (mode === "notification") { root.startPick(); return "ok" }
      if (["region", "window", "error", "clipboard"].indexOf(mode) < 0) return "unsupported-mode: " + mode
      root.startCapture(mode)
      return "ok"
    }
    // A fixed area, "x,y WxH" in screen coordinates. For scripts and tests.
    function captureRegion(geometry: string): string {
      root.startCapture("region", String(geometry || ""))
      return "ok"
    }
    function resend(): string { root.resend(); return "ok" }
    function settings(): string { root.showPage("settings"); return "ok" }
    function history(): string { root.showPage("history"); return "ok" }
    function state(): string {
      return JSON.stringify({ view: root.view, phase: root.phase, opened: root.opened, agent: root.target.agent || "",
        cwd: root.target.cwd || "", masked: root.maskedFindings.length, error: root.errorCode })
    }
  }

  onOpenedChanged: {
    if (opened) {
      Qt.callLater(function() { if (panel.loadedContent) panel.loadedContent.focusQuestion() })
    } else if (phase !== "capturing" && phase !== "sending") {
      clearError()
    }
  }

  // -------------------------------------------------------------- bar icon

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: root.glyphSend
    foreground: root.phase === "ready" ? root.accent : root.barFg
    dimmed: root.phase === "capturing" && pulse.dimPhase
    tooltipText: root.phase === "capturing" ? strings.t("tooltip.busy")
      : root.phase === "ready" ? strings.t("tooltip.ready")
      : strings.t("tooltip.idle")
    onPressed: function(buttonCode) {
      if (buttonCode === Qt.RightButton) root.showPage("history")
      else root.toggle()
    }
  }

  Timer {
    id: pulse
    property bool dimPhase: false
    interval: 520
    repeat: true
    running: root.phase === "capturing" && !Style.reduceMotion
    onTriggered: dimPhase = !dimPhase
    onRunningChanged: if (!running) dimPhase = false
  }

  // ----------------------------------------------------------------- panel

  KeyboardPanel {
    id: panel
    anchorItem: button
    owner: root
    bar: root.bar
    open: root.opened
    focusTarget: panel.loadedContent
    contentWidth: panel.fittedContentWidth(Style.space(560))
    contentHeight: panel.fittedContentHeight(panel.loadedContentHeight, Style.space(820))

    content: FocusScope {
      id: body
      anchors.fill: parent
      readonly property int gap: Style.space(12)
      implicitHeight: column.implicitHeight

      function focusQuestion() {
        if (root.view === "ready") questionField.forceActiveFocus()
        else body.forceActiveFocus()
      }

      Keys.onEscapePressed: root.close()
      Keys.onPressed: function(event) {
        if (root.view === "pick") {
          if (event.key === Qt.Key_Down || event.key === Qt.Key_J) root.pickIndex = Math.min(root.pickItems.length - 1, root.pickIndex + 1)
          else if (event.key === Qt.Key_Up || event.key === Qt.Key_K) root.pickIndex = Math.max(0, root.pickIndex - 1)
          else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) root.choose(root.pickIndex)
          else return
          event.accepted = true
          return
        }
        if (root.view === "history") {
          var n = root.historyItems.length
          if (event.key === Qt.Key_Down || event.key === Qt.Key_J) root.historyIndex = Math.min(n - 1, root.historyIndex + 1)
          else if (event.key === Qt.Key_Up || event.key === Qt.Key_K) root.historyIndex = Math.max(0, root.historyIndex - 1)
          else if ((event.key === Qt.Key_Return || event.key === Qt.Key_Enter) && n > 0) root.sendAgain(root.historyItems[root.historyIndex].id)
          else if (event.key === Qt.Key_Delete && n > 0) root.removeHistory(root.historyItems[root.historyIndex].id)
          else return
          event.accepted = true
          return
        }
        if (root.view !== "ready") return
        var ctrl = (event.modifiers & Qt.ControlModifier) !== 0
        if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
          if (ctrl) root.copy()
          else if (!contextBox.activeFocus) root.send()
          else return
          event.accepted = true
        }
      }

      Column {
        id: column
        width: parent.width
        spacing: body.gap

        // Header: who gets it, and where
        Item {
          width: parent.width
          implicitHeight: Math.max(heroGlyph.height, heroLabels.implicitHeight)
          height: implicitHeight

          Item {
            id: heroGlyph
            width: Style.space(48)
            height: Style.space(48)
            anchors.verticalCenter: parent.verticalCenter

            Text {
              textFormat: Text.PlainText
              anchors.centerIn: parent
              visible: !root.busy
              text: root.view === "error" || root.view === "noagent" ? root.glyphWarn
                : root.view === "done" ? root.glyphOk : root.glyphSend
              color: root.view === "error" || root.view === "noagent" ? root.warn : root.accent
              font.family: root.fontFamily
              font.pixelSize: Style.fontPx(3.2)
            }

            Spinner {
              anchors.centerIn: parent
              visible: root.busy
              size: Style.space(32)
            }
          }

          Column {
            id: heroLabels
            anchors.left: heroGlyph.right
            anchors.leftMargin: Style.space(12)
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            spacing: Style.space(2)

            Text {
              textFormat: Text.PlainText
              width: parent.width
              text: root.view === "error" ? strings.t("error." + root.errorCode, strings.t("error.generic"))
                : root.view === "capturing" ? strings.t("capturing.title")
                : root.view === "pick" ? strings.t("pick.title")
                : root.view === "sending" ? strings.t("sending.title").arg(String(root.target.display || ""))
                : root.view === "done" ? (root.phase === "copied" ? strings.t("copied.title")
                    : strings.t("sent.title").arg(String(root.target.display || "")))
                : root.view === "noagent" ? strings.t("error.no-default-agent")
                : strings.t("title")
              color: root.fg
              font.family: root.fontFamily
              font.pixelSize: Style.font.display
              font.bold: true
              elide: Text.ElideRight
            }

            Text {
              textFormat: Text.PlainText
              width: parent.width
              visible: text !== ""
              text: root.view === "ready" || root.view === "sending" || root.view === "done"
                ? strings.t("sending.to").arg(String(root.target.display || "")).arg(String(root.target.cwd_display || ""))
                : ""
              color: root.view === "ready" ? root.accent : root.dim
              font.family: root.fontFamily
              font.pixelSize: Style.font.body
              elide: Text.ElideMiddle
            }
          }
        }

        PanelSeparator { foreground: root.fg }

        // Tabs, shown on the three pages
        Row {
          visible: root.view === "idle" || root.view === "history" || root.view === "settings"
          width: parent.width
          spacing: Style.spacing.controlGap

          Repeater {
            model: ["menu", "history", "settings"]
            Button {
              required property string modelData
              width: (column.width - Style.spacing.controlGap * 2) / 3
              text: strings.t(modelData === "menu" ? "tab.capture" : "tab." + modelData)
              bordered: true
              focusable: true
              selected: (root.pageActive ? root.page : "menu") === modelData
              foreground: root.fg
              onClicked: root.showPage(modelData)
              Keys.onEscapePressed: root.close()
            }
          }
        }

        // Idle: choose what to capture
        StateNote {
          visible: root.view === "idle"
          glyph: root.glyphSend
          glyphColor: root.faint
          title: strings.t("idle.title")
          text: strings.t("idle.body")
        }

        Column {
          visible: root.view === "idle"
          width: parent.width
          spacing: Style.space(8)

          Button {
            width: parent.width
            text: strings.t("mode.region")
            bordered: true
            focusable: true
            selected: true
            foreground: root.fg
            onClicked: root.startCapture("region")
            Keys.onEscapePressed: root.close()
          }
          Button {
            width: parent.width
            text: strings.t("mode.window")
            bordered: true
            focusable: true
            foreground: root.fg
            onClicked: root.startCapture("window")
            Keys.onEscapePressed: root.close()
          }
          Button {
            width: parent.width
            text: strings.t("mode.error")
            bordered: true
            focusable: true
            foreground: root.fg
            onClicked: root.startCapture("error")
            Keys.onEscapePressed: root.close()
          }
          Button {
            width: parent.width
            text: strings.t("mode.notification")
            bordered: true
            focusable: true
            foreground: root.fg
            onClicked: root.startPick()
            Keys.onEscapePressed: root.close()
          }
          Button {
            width: parent.width
            text: strings.t("mode.clipboard")
            bordered: true
            focusable: true
            foreground: root.fg
            onClicked: root.startCapture("clipboard")
            Keys.onEscapePressed: root.close()
          }
        }

        // Capturing
        StateNote {
          visible: root.view === "capturing"
          title: ""
          text: strings.t("capturing.body")
        }

        // History
        Column {
          visible: root.view === "history"
          width: parent.width
          spacing: Style.space(6)

          StateNote {
            visible: root.historyItems.length === 0
            title: strings.t("history.empty.title")
            text: strings.t("history.empty.body")
          }

          Flickable {
            id: historyFlick
            visible: root.historyItems.length > 0
            width: parent.width
            height: Math.min(historyList.implicitHeight, Style.space(430))
            contentWidth: width
            contentHeight: historyList.implicitHeight
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            interactive: contentHeight > height
            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

            Column {
              id: historyList
              width: historyFlick.width - (historyFlick.interactive ? Style.space(10) : 0)
              spacing: Style.space(6)

              Repeater {
                model: root.historyItems
                BorderSurface {
                  id: hrow
                  required property var modelData
                  required property int index
                  width: historyList.width
                  implicitHeight: Math.max(hthumb.height, htext.implicitHeight) + Style.space(14)
                  height: implicitHeight
                  radius: Style.cornerRadius
                  readonly property bool current: index === root.historyIndex
                  color: current ? Qt.rgba(root.accent.r, root.accent.g, root.accent.b, 0.14) : "transparent"
                  borderSpec: Border.flat(current ? root.accent : Qt.rgba(root.fg.r, root.fg.g, root.fg.b, 0.2),
                                          Math.max(1, Style.normalBorderWidth))

                  MouseArea {
                    anchors.fill: parent
                    hoverEnabled: true
                    onEntered: root.historyIndex = hrow.index
                  }

                  Rectangle {
                    id: hthumb
                    anchors.left: parent.left
                    anchors.leftMargin: Style.space(8)
                    anchors.verticalCenter: parent.verticalCenter
                    width: Style.space(64)
                    height: Style.space(44)
                    radius: Style.cornerRadius
                    color: Style.normalFillFor(root.fg, root.accent)
                    clip: true

                    Image {
                      anchors.fill: parent
                      visible: hrow.modelData.thumb !== ""
                      source: hrow.modelData.thumb !== "" ? "file://" + hrow.modelData.thumb : ""
                      fillMode: Image.PreserveAspectCrop
                      asynchronous: true
                      sourceSize.width: 200
                      cache: false
                    }

                    Text {
                      anchors.centerIn: parent
                      visible: hrow.modelData.thumb === ""
                      textFormat: Text.PlainText
                      text: strings.t("modeShort." + hrow.modelData.mode, strings.t("history.noImage"))
                      color: root.dim
                      font.family: root.fontFamily
                      font.pixelSize: Style.font.caption
                    }
                  }

                  Column {
                    id: htext
                    anchors.left: hthumb.right
                    anchors.leftMargin: Style.space(10)
                    anchors.right: hactions.left
                    anchors.rightMargin: Style.space(8)
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: Style.space(2)

                    Text {
                      textFormat: Text.PlainText
                      width: parent.width
                      text: hrow.modelData.display + "  ·  " + hrow.modelData.cwd.replace(/^\/home\/[^/]+/, "~")
                      color: hrow.current ? root.accent : root.fg
                      font.family: root.fontFamily
                      font.pixelSize: Style.font.body
                      font.bold: true
                      elide: Text.ElideMiddle
                    }
                    Text {
                      textFormat: Text.PlainText
                      width: parent.width
                      text: Qt.formatDateTime(new Date(hrow.modelData.time * 1000), "yyyy-MM-dd hh:mm") + "  ·  "
                            + strings.t("modeShort." + hrow.modelData.mode, hrow.modelData.mode)
                            + (hrow.modelData.question ? "  ·  " + hrow.modelData.question : "")
                      color: root.dim
                      font.family: root.fontFamily
                      font.pixelSize: Style.font.bodySmall
                      elide: Text.ElideRight
                    }
                  }

                  Row {
                    id: hactions
                    anchors.right: parent.right
                    anchors.rightMargin: Style.space(8)
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: Style.space(6)

                    Button {
                      text: strings.t("history.sendAgain")
                      bordered: true
                      focusable: true
                      enabled: hrow.modelData.available
                      opacity: enabled ? 1 : 0.45
                      foreground: root.fg
                      onClicked: root.sendAgain(hrow.modelData.id)
                      Keys.onEscapePressed: root.close()
                    }
                    Button {
                      text: strings.t("history.delete")
                      bordered: true
                      focusable: true
                      foreground: root.warn
                      onClicked: root.removeHistory(hrow.modelData.id)
                      Keys.onEscapePressed: root.close()
                    }
                  }
                }
              }
            }
          }

          Text {
            visible: root.historyItems.length > 0
            textFormat: Text.PlainText
            width: parent.width
            text: strings.t("history.hint")
            color: root.faint
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
            horizontalAlignment: Text.AlignHCenter
          }
        }

        // Settings
        Flickable {
          id: settingsFlick
          visible: root.view === "settings" && root.cfg !== null
          width: parent.width
          height: visible ? Math.min(settingsBody.implicitHeight, Style.space(500)) : 0
          contentWidth: width
          contentHeight: settingsBody.implicitHeight
          clip: true
          boundsBehavior: Flickable.StopAtBounds
          interactive: contentHeight > height
          ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

          Column {
            id: settingsBody
            width: settingsFlick.width - (settingsFlick.interactive ? Style.space(10) : 0)
            spacing: Style.space(12)

            Toggle {
              width: parent.width
              label: strings.t("settings.ocr")
              description: strings.t("settings.ocr.desc")
              checked: root.cfg ? root.cfg.ocr : true
              foreground: root.fg
              accent: root.accent
              onClicked: root.setCfg(["ocr"], !root.cfg.ocr)
            }

            Toggle {
              width: parent.width
              label: strings.t("settings.auto")
              description: strings.t("settings.auto.desc")
              checked: root.cfg ? root.cfg.agent_auto : false
              foreground: root.fg
              accent: root.warn
              onClicked: root.setCfg(["agent_auto"], !root.cfg.agent_auto)
            }

            NumberField {
              width: parent.width
              label: strings.t("settings.retention")
              value: root.cfg ? root.cfg.retention_days : 7
              from: 0
              to: 3650
              foreground: root.fg
              accent: root.accent
              onModified: function(v) { root.setCfg(["retention_days"], v) }
            }

            NumberField {
              width: parent.width
              label: strings.t("settings.maxEdge")
              value: root.cfg ? root.cfg.image.max_edge : 1920
              from: 200
              to: 8000
              stepSize: 100
              foreground: root.fg
              accent: root.accent
              onModified: function(v) { root.setCfg(["image", "max_edge"], v) }
            }

            NumberField {
              width: parent.width
              label: strings.t("settings.maxMb")
              value: root.cfg ? Math.round(root.cfg.image.max_bytes / 1000000) : 2
              from: 1
              to: 20
              foreground: root.fg
              accent: root.accent
              onModified: function(v) { root.setCfg(["image", "max_bytes"], v * 1000000) }
            }

            PanelSeparator { foreground: root.fg }

            Text {
              textFormat: Text.PlainText
              width: parent.width
              text: strings.t("settings.questions")
              color: root.fg
              font.family: root.fontFamily
              font.pixelSize: Style.font.body
              font.bold: true
            }

            Repeater {
              model: ["region", "window", "error", "notification", "clipboard"]
              Column {
                id: qrow
                required property string modelData
                width: settingsBody.width
                spacing: Style.space(3)

                Text {
                  textFormat: Text.PlainText
                  text: strings.t("modeShort." + qrow.modelData)
                  color: root.dim
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.bodySmall
                }
                TextField {
                  id: qfield
                  width: parent.width
                  foreground: root.fg
                  placeholderText: strings.t("question.default." + qrow.modelData)
                  maximumLength: 500
                  selectByMouse: true
                  function refill() { text = root.cfg && root.cfg.questions[qrow.modelData] ? root.cfg.questions[qrow.modelData] : "" }
                  Component.onCompleted: refill()
                  onTextEdited: {
                    var q = JSON.parse(JSON.stringify(root.cfg.questions))
                    if (text.trim() === "") delete q[qrow.modelData]
                    else q[qrow.modelData] = text
                    root.setCfg(["questions"], q)
                  }
                  Connections { target: root; function onCfgStampChanged() { qfield.refill() } }
                  Keys.onEscapePressed: root.close()
                }
              }
            }

            Text {
              textFormat: Text.PlainText
              width: parent.width
              text: strings.t("settings.questions.hint")
              color: root.faint
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
            }

            PanelSeparator { foreground: root.fg }

            Text {
              textFormat: Text.PlainText
              width: parent.width
              text: strings.t("settings.blocklist")
              color: root.fg
              font.family: root.fontFamily
              font.pixelSize: Style.font.body
              font.bold: true
            }

            Column {
              width: parent.width
              spacing: Style.space(3)
              Text {
                textFormat: Text.PlainText
                text: strings.t("settings.blocklist.classes")
                color: root.dim
                font.family: root.fontFamily
                font.pixelSize: Style.font.bodySmall
              }
              TextField {
                id: classesField
                width: parent.width
                foreground: root.fg
                selectByMouse: true
                function refill() { text = root.cfg ? root.cfg.blocklist.classes.join(", ") : "" }
                Component.onCompleted: refill()
                onTextEdited: root.setCfg(["blocklist", "classes"], root.listFrom(text))
                Connections { target: root; function onCfgStampChanged() { classesField.refill() } }
                Keys.onEscapePressed: root.close()
              }
            }

            Column {
              width: parent.width
              spacing: Style.space(3)
              Text {
                textFormat: Text.PlainText
                text: strings.t("settings.blocklist.titles")
                color: root.dim
                font.family: root.fontFamily
                font.pixelSize: Style.font.bodySmall
              }
              TextField {
                id: titlesField
                width: parent.width
                foreground: root.fg
                selectByMouse: true
                function refill() { text = root.cfg ? root.cfg.blocklist.titles.join(", ") : "" }
                Component.onCompleted: refill()
                onTextEdited: root.setCfg(["blocklist", "titles"], root.listFrom(text))
                Connections { target: root; function onCfgStampChanged() { titlesField.refill() } }
                Keys.onEscapePressed: root.close()
              }
            }

            PanelSeparator { foreground: root.fg }

            Column {
              id: hookCol
              width: parent.width
              spacing: Style.space(6)
              readonly property bool installed: !!root.hookStatus.bash || !!root.hookStatus.zsh

              Text {
                textFormat: Text.PlainText
                width: parent.width
                text: strings.t("settings.hook")
                color: root.fg
                font.family: root.fontFamily
                font.pixelSize: Style.font.body
                font.bold: true
              }
              Text {
                textFormat: Text.PlainText
                width: parent.width
                text: (hookCol.installed ? strings.t("settings.hook.on") : strings.t("settings.hook.off"))
                      + (root.settingsNote === "hook" ? "  " + strings.t("settings.hook.done") : "")
                color: root.dim
                font.family: root.fontFamily
                font.pixelSize: Style.font.bodySmall
                wrapMode: Text.WordWrap
              }
              Text {
                visible: root.hookConfirm
                textFormat: Text.PlainText
                width: parent.width
                text: strings.t("settings.hook.confirm")
                color: root.fg
                font.family: root.fontFamily
                font.pixelSize: Style.font.bodySmall
                wrapMode: Text.WordWrap
              }
              Row {
                spacing: Style.spacing.controlGap
                Button {
                  visible: !hookCol.installed && !root.hookConfirm
                  text: strings.t("settings.hook.install")
                  bordered: true
                  focusable: true
                  foreground: root.fg
                  onClicked: root.hookConfirm = true
                  Keys.onEscapePressed: root.close()
                }
                Button {
                  visible: !hookCol.installed && root.hookConfirm
                  text: strings.t("settings.hook.install")
                  bordered: true
                  focusable: true
                  selected: true
                  foreground: root.fg
                  onClicked: root.setHook(true)
                  Keys.onEscapePressed: root.hookConfirm = false
                }
                Button {
                  visible: !hookCol.installed && root.hookConfirm
                  text: strings.t("button.cancel")
                  bordered: true
                  focusable: true
                  foreground: root.fg
                  onClicked: root.hookConfirm = false
                  Keys.onEscapePressed: root.hookConfirm = false
                }
                Button {
                  visible: hookCol.installed
                  text: strings.t("settings.hook.remove")
                  bordered: true
                  focusable: true
                  foreground: root.fg
                  onClicked: root.setHook(false)
                  Keys.onEscapePressed: root.close()
                }
              }
            }

            Text {
              textFormat: Text.PlainText
              width: parent.width
              text: strings.t("settings.file").arg(root.cfgPath.replace(/^\/home\/[^/]+/, "~"))
              color: root.faint
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
              wrapMode: Text.WrapAnywhere
            }
          }
        }

        RowLayout {
          visible: root.view === "settings" && root.cfg !== null
          width: parent.width
          spacing: Style.spacing.controlGap

          Text {
            textFormat: Text.PlainText
            Layout.fillWidth: true
            text: root.settingsNote === "saved" ? strings.t("settings.saved") : (root.settingsNote === "failed" ? strings.t("settings.failed") : "")
            color: root.settingsNote === "failed" ? root.warn : root.accent
            font.family: root.fontFamily
            font.pixelSize: Style.font.bodySmall
          }
          Button {
            text: strings.t("settings.reset")
            bordered: true
            focusable: true
            foreground: root.fg
            onClicked: settingsResetProc.running = true
            Keys.onEscapePressed: root.close()
          }
          Button {
            text: strings.t("settings.save")
            bordered: true
            focusable: true
            selected: true
            foreground: root.fg
            onClicked: root.saveSettings()
            Keys.onEscapePressed: root.close()
          }
        }

        // Notification picker
        Column {
          visible: root.view === "pick"
          width: parent.width
          spacing: Style.space(6)

          StateNote {
            visible: root.pickItems.length === 0
            title: ""
            text: strings.t("pick.loading")
          }

          Repeater {
            model: root.pickItems
            BorderSurface {
              id: pickRow
              required property var modelData
              required property int index
              width: column.width
              implicitHeight: pickText.implicitHeight + Style.space(14)
              height: implicitHeight
              radius: Style.cornerRadius
              readonly property bool current: index === root.pickIndex
              color: current ? Qt.rgba(root.accent.r, root.accent.g, root.accent.b, 0.14) : "transparent"
              borderSpec: Border.flat(current ? root.accent : Qt.rgba(root.fg.r, root.fg.g, root.fg.b, 0.2),
                                      Math.max(1, Style.normalBorderWidth))

              Column {
                id: pickText
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                anchors.leftMargin: Style.space(10)
                anchors.rightMargin: Style.space(10)
                spacing: Style.space(2)

                Text {
                  textFormat: Text.PlainText
                  width: parent.width
                  text: (pickRow.modelData.app ? pickRow.modelData.app + "  ·  " : "") + pickRow.modelData.summary
                  color: pickRow.current ? root.accent : root.fg
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.body
                  font.bold: true
                  elide: Text.ElideRight
                }
                Text {
                  textFormat: Text.PlainText
                  width: parent.width
                  text: pickRow.modelData.time + (pickRow.modelData.body ? "  ·  " + pickRow.modelData.body.replace(/\s+/g, " ") : "")
                  color: root.dim
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.bodySmall
                  elide: Text.ElideRight
                }
              }

              MouseArea {
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onEntered: root.pickIndex = pickRow.index
                onClicked: root.choose(pickRow.index)
              }
            }
          }

          Text {
            visible: root.pickItems.length > 0
            textFormat: Text.PlainText
            width: parent.width
            text: strings.t("pick.hint")
            color: root.faint
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
            horizontalAlignment: Text.AlignHCenter
          }
        }

        // Error and no-agent states
        StateNote {
          visible: root.view === "error"
          title: ""
          text: strings.t("error." + root.errorCode + ".body", root.errorMessage !== "" ? root.errorMessage : strings.t("error.hint"))
          hint: strings.t("error.hint")
          mono: true
        }

        StateNote {
          visible: root.view === "noagent"
          glyph: root.glyphWarn
          glyphColor: root.warn
          title: ""
          text: strings.t("defaults." + String(root.target.problem || "missing-file"), strings.t("error.no-default-agent.body"))
          hint: strings.t("error.no-default-agent.body")
        }

        Button {
          visible: root.view === "noagent"
          width: parent.width
          text: strings.t("button.agentSetup")
          bordered: true
          focusable: true
          selected: true
          foreground: root.fg
          onClicked: root.openAgentSetup()
          Keys.onEscapePressed: root.close()
        }

        // Done
        StateNote {
          visible: root.view === "done"
          glyph: root.glyphOk
          glyphColor: root.accent
          title: ""
          text: root.phase === "sent" ? strings.t("sent.body") : ""
        }

        // Ready: thumbnail, notes, question, masks, context, buttons
        Item {
          id: thumbBox
          visible: (root.view === "ready" || root.view === "sending") && root.hasImage && root.sendImage
          readonly property real framePad: Style.space(10)
          readonly property real maxH: Style.space(190)
          readonly property bool known: thumb.implicitWidth > 0 && thumb.implicitHeight > 0
          // From the picture's own size, so the frame never depends on what is painted.
          readonly property real fit: known ? Math.min((width - framePad) / thumb.implicitWidth,
                                                       (maxH - framePad) / thumb.implicitHeight, 1.6) : 1
          width: parent.width
          height: visible ? (known ? Math.round(thumb.implicitHeight * fit + framePad) : Style.space(70)) : 0

          BorderSurface {
            anchors.horizontalCenter: parent.horizontalCenter
            width: thumbBox.known ? Math.round(thumb.implicitWidth * thumbBox.fit + thumbBox.framePad) : Style.space(120)
            height: parent.height
            radius: Style.cornerRadius
            color: Style.normalFillFor(root.fg, root.accent)
            borderSpec: Border.flat(Qt.rgba(root.accent.r, root.accent.g, root.accent.b, 0.5), Math.max(1, Style.normalBorderWidth))

            Image {
              id: thumb
              anchors.fill: parent
              anchors.margins: thumbBox.framePad / 2
              source: root.snap && root.snap.capture ? "file://" + root.snap.capture.path : ""
              fillMode: Image.PreserveAspectFit
              asynchronous: true
              sourceSize.width: 1100
              cache: false
            }

            // A short flash of the accent colour when the capture arrives.
            Rectangle {
              id: flash
              anchors.fill: parent
              radius: Style.cornerRadius
              color: root.accent
              opacity: 0
              SequentialAnimation on opacity {
                id: flashAnim
                running: false
                NumberAnimation { to: 0.35; duration: Style.duration(70) }
                NumberAnimation { to: 0; duration: Style.duration(380); easing.type: Easing.OutCubic }
              }
              Connections {
                target: root
                function onFlashStampChanged() { if (!Style.reduceMotion) flashAnim.restart() }
              }
            }
          }
        }

        Column {
          visible: root.view === "ready" && notes.length > 0
          width: parent.width
          spacing: Style.space(2)
          readonly property var notes: root.hasPreview ? (root.preview.notes || []) : []

          Repeater {
            model: parent.notes
            Text {
              required property string modelData
              textFormat: Text.PlainText
              width: column.width
              text: strings.t("note." + modelData, "")
              visible: text !== ""
              color: (modelData === "agent_not_installed" || modelData === "auto_mode") ? root.warn : root.dim
              font.family: root.fontFamily
              font.pixelSize: Style.font.bodySmall
              wrapMode: Text.WordWrap
              lineHeight: 1.2
            }
          }
        }

        // The screenshot seems to show secrets
        BorderSurface {
          visible: root.view === "ready" && root.hasImage && root.imageSecrets.length > 0
          width: parent.width
          implicitHeight: imageWarn.implicitHeight + Style.space(20)
          height: implicitHeight
          radius: Style.cornerRadius
          color: Qt.rgba(root.warn.r, root.warn.g, root.warn.b, 0.10)
          borderSpec: Border.flat(Qt.rgba(root.warn.r, root.warn.g, root.warn.b, 0.6), Math.max(1, Style.normalBorderWidth))

          Column {
            id: imageWarn
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            anchors.margins: Style.space(10)
            spacing: Style.space(8)

            Text {
              textFormat: Text.PlainText
              width: parent.width
              text: root.sendImage ? strings.t("imagesecrets.warn").arg(root.imageSecrets.join(", "))
                                   : strings.t("imagesecrets.textonly")
              color: root.warn
              font.family: root.fontFamily
              font.pixelSize: Style.font.bodySmall
              font.bold: true
              wrapMode: Text.WordWrap
            }

            Button {
              text: root.sendImage ? strings.t("imagesecrets.sendText") : strings.t("imagesecrets.includeImage")
              bordered: true
              focusable: true
              foreground: root.fg
              onClicked: root.setSendImage(!root.sendImage)
              Keys.onEscapePressed: root.close()
            }
          }
        }

        Column {
          visible: root.view === "ready"
          width: parent.width
          spacing: Style.space(6)

          Text {
            textFormat: Text.PlainText
            text: strings.t("question.label")
            color: root.dim
            font.family: root.fontFamily
            font.pixelSize: Style.font.bodySmall
          }

          TextField {
            id: questionField
            width: parent.width
            foreground: root.fg
            placeholderText: root.hasPreview && root.preview.default_source === "builtin" && root.snap
              ? strings.t("question.default." + root.snap.mode, root.preview.question)
              : (root.hasPreview && root.preview.question ? root.preview.question : strings.t("question.placeholder"))
            maximumLength: 2000
            selectByMouse: true
            onTextChanged: {
              if (root.question !== text) {
                root.question = text
                recompose.restart()
              }
            }
            onAccepted: root.send()
            Keys.onEscapePressed: root.close()
            Connections {
              target: root
              function onQuestionChanged() { if (questionField.text !== root.question) questionField.text = root.question }
            }
            Keys.onPressed: function(event) {
              if ((event.key === Qt.Key_Return || event.key === Qt.Key_Enter) && (event.modifiers & Qt.ControlModifier)) {
                root.copy()
                event.accepted = true
              }
            }
          }
        }

        // Masked secrets, in the theme's warning colour
        Column {
          visible: root.view === "ready" && root.maskedFindings.length > 0
          width: parent.width
          spacing: Style.space(6)

          Text {
            textFormat: Text.PlainText
            width: parent.width
            text: strings.tn("masked.title", root.maskedFindings.length).arg(root.maskedFindings.length)
            color: root.warn
            font.family: root.fontFamily
            font.pixelSize: Style.font.bodySmall
            font.bold: true
          }

          Flow {
            width: parent.width
            spacing: Style.space(6)

            Repeater {
              model: root.maskedFindings
              BorderSurface {
                id: maskChip
                required property var modelData
                implicitWidth: maskLabel.implicitWidth + Style.space(16)
                implicitHeight: maskLabel.implicitHeight + Style.space(8)
                radius: Style.cornerRadius
                color: maskMouse.containsMouse ? Qt.rgba(root.warn.r, root.warn.g, root.warn.b, 0.24)
                                               : Qt.rgba(root.warn.r, root.warn.g, root.warn.b, 0.12)
                borderSpec: Border.flat(Qt.rgba(root.warn.r, root.warn.g, root.warn.b, 0.55), Math.max(1, Style.normalBorderWidth))

                Text {
                  id: maskLabel
                  textFormat: Text.PlainText
                  anchors.centerIn: parent
                  text: modelData.kind + " #" + modelData.id
                  color: root.warn
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.caption
                  font.bold: true
                }

                MouseArea {
                  id: maskMouse
                  anchors.fill: parent
                  hoverEnabled: true
                  cursorShape: Qt.PointingHandCursor
                  onClicked: root.undoMask(maskChip.modelData.id)
                }
              }
            }
          }

          Text {
            textFormat: Text.PlainText
            width: parent.width
            text: strings.t("masked.undo") + (root.contextEdited ? "  ·  " + strings.t("masked.reset") : "")
            color: root.faint
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
            wrapMode: Text.WordWrap
          }
        }

        // Context, collapsible
        Column {
          visible: root.view === "ready"
          width: parent.width
          spacing: Style.space(6)

          Item {
            id: contextHeader
            width: parent.width
            height: contextLabel.implicitHeight + Style.space(8)
            activeFocusOnTab: true
            Keys.onEscapePressed: root.close()
            Keys.onPressed: function(event) {
              if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter || event.key === Qt.Key_Space) {
                if (event.modifiers & Qt.ControlModifier) root.copy()
                else root.contextOpen = !root.contextOpen
                event.accepted = true
              }
            }

            Row {
              spacing: Style.space(8)
              anchors.verticalCenter: parent.verticalCenter

              Text {
                textFormat: Text.PlainText
                text: root.glyphChevron
                color: contextHeader.activeFocus ? root.accent : root.dim
                rotation: root.contextOpen ? 90 : 0
                font.family: root.fontFamily
                font.pixelSize: Style.font.body
                Behavior on rotation { NumberAnimation { duration: Style.duration(140); easing.type: Easing.OutCubic } }
              }
              Text {
                id: contextLabel
                textFormat: Text.PlainText
                text: strings.t("context.label") + (root.contextEdited ? "  ·  " + strings.t("context.edited") : "")
                color: contextHeader.activeFocus ? root.accent : root.fg
                font.family: root.fontFamily
                font.pixelSize: Style.font.body
                font.bold: true
              }
            }

            MouseArea {
              anchors.fill: parent
              cursorShape: Qt.PointingHandCursor
              onClicked: root.contextOpen = !root.contextOpen
            }
          }

          Rectangle {
            id: contextFrame
            visible: root.contextOpen
            width: parent.width
            height: visible ? Style.space(260) : 0
            radius: Style.cornerRadius
            color: Style.normalFillFor(root.fg, root.accent)
            border.width: Math.max(1, Style.normalBorderWidth)
            border.color: contextBox.activeFocus ? root.accent : Qt.rgba(root.fg.r, root.fg.g, root.fg.b, 0.2)
            clip: true

            Flickable {
              id: contextFlick
              anchors.fill: parent
              anchors.margins: Style.space(8)
              contentWidth: width
              contentHeight: contextBox.implicitHeight
              clip: true
              boundsBehavior: Flickable.StopAtBounds
              ScrollBar.vertical: ScrollBar { policy: contextFlick.contentHeight > contextFlick.height ? ScrollBar.AlwaysOn : ScrollBar.AlwaysOff }

              TextEdit {
                id: contextBox
                width: contextFlick.width - Style.space(10)
                textFormat: TextEdit.PlainText
                wrapMode: TextEdit.Wrap
                selectByMouse: true
                color: root.fg
                selectionColor: root.accent
                selectedTextColor: Commons.Color.popups.background
                font.family: root.fontFamily
                font.pixelSize: Style.font.bodySmall
                text: root.contextText
                Keys.onEscapePressed: root.close()
                Keys.priority: Keys.BeforeItem
                Keys.onPressed: function(event) {
                  if ((event.key === Qt.Key_Return || event.key === Qt.Key_Enter) && (event.modifiers & Qt.ControlModifier)) {
                    root.copy()
                    event.accepted = true
                  }
                }
                onTextChanged: {
                  if (text !== root.contextText) {
                    root.contextText = text
                    root.contextEdited = true
                    recompose.restart()
                  }
                }
              }
            }
          }
        }

        PanelSeparator {
          visible: root.view === "ready" || root.view === "noagent"
          foreground: root.fg
        }

        Text {
          visible: root.view === "ready"
          textFormat: Text.PlainText
          width: parent.width
          text: strings.t("hint.keys")
          color: root.faint
          font.family: root.fontFamily
          font.pixelSize: Style.font.caption
          horizontalAlignment: Text.AlignHCenter
        }

        RowLayout {
          visible: root.view === "ready" || root.view === "error"
          width: parent.width
          spacing: Style.spacing.controlGap

          Item { Layout.fillWidth: true }

          Button {
            text: strings.t("button.cancel")
            bordered: true
            focusable: true
            foreground: root.fg
            onClicked: { root.close(); if (root.view === "error") root.clearError() }
            Keys.onEscapePressed: root.close()
          }

          Button {
            visible: root.view === "ready"
            text: strings.t("button.copy")
            bordered: true
            focusable: true
            foreground: root.fg
            onClicked: root.copy()
            Keys.onEscapePressed: root.close()
          }

          Button {
            visible: root.view === "ready"
            text: strings.t("button.send")
            iconText: root.glyphSend
            bordered: true
            focusable: true
            selected: true
            enabled: root.canSend
            opacity: enabled ? 1 : 0.45
            foreground: root.fg
            onClicked: root.send()
            Keys.onEscapePressed: root.close()
          }
        }
      }
    }
  }

  // ------------------------------------------------------------ components

  // A ring with a dot running round it. Constant motion, so linear.
  component Spinner: Item {
    id: spinner
    property real size: Style.space(28)
    width: size
    height: size

    Rectangle {
      anchors.fill: parent
      radius: width / 2
      color: "transparent"
      border.width: Math.max(2, Style.space(3))
      border.color: Qt.rgba(root.fg.r, root.fg.g, root.fg.b, 0.16)
    }

    Item {
      anchors.fill: parent
      RotationAnimation on rotation {
        from: 0
        to: 360
        duration: 900
        loops: Animation.Infinite
        running: spinner.visible && !Style.reduceMotion
      }

      Rectangle {
        width: Math.max(4, Style.space(7))
        height: width
        radius: width / 2
        color: root.accent
        anchors.horizontalCenter: parent.horizontalCenter
        y: -Math.round(width / 4)
      }
    }
  }

  // Centered message for the idle, capturing, error and done states.
  component StateNote: Column {
    id: note
    property string glyph: ""
    property color glyphColor: root.dim
    property string title: ""
    property string text: ""
    property string hint: ""
    property bool mono: false

    width: parent ? parent.width : implicitWidth
    topPadding: Style.space(10)
    bottomPadding: Style.space(12)
    spacing: Style.space(8)

    Text {
      textFormat: Text.PlainText
      visible: note.glyph !== ""
      anchors.horizontalCenter: parent.horizontalCenter
      text: note.glyph
      color: note.glyphColor
      font.family: root.fontFamily
      font.pixelSize: Style.fontPx(3.0)
    }

    Text {
      textFormat: Text.PlainText
      visible: note.title !== ""
      width: parent.width
      horizontalAlignment: Text.AlignHCenter
      text: note.title
      color: root.fg
      font.family: root.fontFamily
      font.pixelSize: Style.font.title
      font.bold: true
      wrapMode: Text.WordWrap
    }

    Text {
      textFormat: Text.PlainText
      visible: note.text !== ""
      width: Math.min(parent.width, Style.space(460))
      anchors.horizontalCenter: parent.horizontalCenter
      horizontalAlignment: Text.AlignHCenter
      text: note.text
      color: root.dim
      font.family: root.fontFamily
      font.pixelSize: note.mono ? Style.font.bodySmall : Style.font.body
      wrapMode: Text.Wrap
      lineHeight: 1.3
      maximumLineCount: 6
      elide: Text.ElideRight
    }

    Text {
      textFormat: Text.PlainText
      visible: note.hint !== "" && note.hint !== note.text
      width: parent.width
      horizontalAlignment: Text.AlignHCenter
      text: note.hint
      color: root.faint
      font.family: root.fontFamily
      font.pixelSize: Style.font.bodySmall
      wrapMode: Text.WordWrap
    }
  }
}

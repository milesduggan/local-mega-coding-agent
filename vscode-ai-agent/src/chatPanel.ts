import * as vscode from "vscode";
import * as path from "path";
import { PythonBackend } from "./pythonBackend";

interface Message {
  role: "user" | "assistant";
  content: string;
}

export class ChatPanel {
  public static currentPanel: ChatPanel | undefined;

  private readonly panel: vscode.WebviewPanel;
  private readonly extensionUri: vscode.Uri;
  private backend: PythonBackend;
  private disposables: vscode.Disposable[] = [];

  private conversationHistory: Message[] = [];
  private selectedFiles: Set<string> = new Set();
  private normalizedTask: string | null = null;

  private constructor(
    panel: vscode.WebviewPanel,
    extensionUri: vscode.Uri,
    backend: PythonBackend
  ) {
    this.panel = panel;
    this.extensionUri = extensionUri;
    this.backend = backend;

    this.panel.webview.html = this.getHtmlContent();

    this.panel.webview.onDidReceiveMessage(
      (message) => this.handleWebviewMessage(message),
      null,
      this.disposables
    );

    this.panel.onDidDispose(() => this.dispose(), null, this.disposables);
  }

  public static createOrShow(
    extensionUri: vscode.Uri,
    backend: PythonBackend
  ): ChatPanel {
    const column = vscode.ViewColumn.Beside;

    if (ChatPanel.currentPanel) {
      ChatPanel.currentPanel.panel.reveal(column);
      return ChatPanel.currentPanel;
    }

    const panel = vscode.window.createWebviewPanel(
      "aiAgentChat",
      "AI Agent Chat",
      column,
      {
        enableScripts: true,
        retainContextWhenHidden: true,
        localResourceRoots: [vscode.Uri.joinPath(extensionUri, "media")],
      }
    );

    ChatPanel.currentPanel = new ChatPanel(panel, extensionUri, backend);
    return ChatPanel.currentPanel;
  }

  public addFile(filePath: string): void {
    this.selectedFiles.add(filePath);
    this.updateFilesList();
  }

  public removeFile(filePath: string): void {
    this.selectedFiles.delete(filePath);
    this.updateFilesList();
  }

  public clearFiles(): void {
    this.selectedFiles.clear();
    this.updateFilesList();
  }

  public getSelectedFiles(): string[] {
    return Array.from(this.selectedFiles);
  }

  private updateFilesList(): void {
    this.panel.webview.postMessage({
      type: "filesUpdated",
      files: Array.from(this.selectedFiles).map((f) => path.basename(f)),
      fullPaths: Array.from(this.selectedFiles),
    });
  }

  private async handleWebviewMessage(message: {
    type: string;
    text?: string;
  }): Promise<void> {
    switch (message.type) {
      case "sendMessage":
        await this.handleUserMessage(message.text || "");
        break;
      case "proceed":
        await this.handleProceed();
        break;
      case "quickExecute":
        await this.handleQuickExecute(message.text || "");
        break;
      case "removeFile":
        if (message.text) {
          this.removeFile(message.text);
        }
        break;
    }
  }

  private async handleUserMessage(text: string): Promise<void> {
    if (!text.trim()) {
      return;
    }

    // Add user message to UI
    this.panel.webview.postMessage({
      type: "addMessage",
      role: "user",
      content: text,
    });

    // Show loading state
    this.panel.webview.postMessage({ type: "setLoading", loading: true });

    try {
      // Get file summaries to include in context
      const fileSummaries = await this.getFileSummaries();
      const messageWithContext = fileSummaries
        ? `${text}\n\n${fileSummaries}`
        : text;

      const response = await this.backend.chat(
        messageWithContext,
        this.conversationHistory
      );

      // Update history (store original message, not with summaries)
      this.conversationHistory.push({ role: "user", content: text });
      this.conversationHistory.push({ role: "assistant", content: response });

      // Add response to UI
      this.panel.webview.postMessage({
        type: "addMessage",
        role: "assistant",
        content: response,
      });

      // Check if critic is done asking questions
      if (!this.looksLikeQuestion(response)) {
        this.normalizedTask = response;
        this.panel.webview.postMessage({
          type: "taskConfirmed",
          task: response,
        });
      }
    } catch (error) {
      const errorMessage =
        error instanceof Error ? error.message : "Unknown error";
      this.panel.webview.postMessage({
        type: "addMessage",
        role: "assistant",
        content: `Error: ${errorMessage}`,
      });
    } finally {
      this.panel.webview.postMessage({ type: "setLoading", loading: false });
    }
  }

  private looksLikeQuestion(text: string): boolean {
    const markers = [
      "?",
      "clarify",
      "confirm",
      "could you",
      "can you",
      "what about",
      "how about",
      "tell me",
      "please explain",
      "more details",
    ];
    const lower = text.toLowerCase();
    return markers.some((m) => lower.includes(m));
  }

  private async handleQuickExecute(task: string): Promise<void> {
    if (!task.trim()) {
      vscode.window.showWarningMessage("Please enter a task description.");
      return;
    }

    if (this.selectedFiles.size === 0) {
      vscode.window.showWarningMessage(
        "No files selected. Right-click files in the explorer to add them."
      );
      return;
    }

    this.panel.webview.postMessage({ type: "setLoading", loading: true });

    // Show the task in UI
    this.panel.webview.postMessage({
      type: "addMessage",
      role: "user",
      content: `[Quick Execute] ${task}`,
    });

    try {
      // Read file contents
      const files: Record<string, string> = {};
      for (const filePath of this.selectedFiles) {
        try {
          const content = await vscode.workspace.fs.readFile(
            vscode.Uri.file(filePath)
          );
          const relativePath = vscode.workspace.asRelativePath(filePath);
          files[relativePath] = Buffer.from(content).toString("utf8");
        } catch (e) {
          vscode.window.showWarningMessage(`Could not read file: ${filePath}`);
        }
      }

      if (Object.keys(files).length === 0) {
        vscode.window.showErrorMessage("No valid files to process.");
        return;
      }

      // Execute directly with the task (skip critic)
      const diff = await this.backend.execute(task, files);

      this.panel.webview.postMessage({
        type: "addMessage",
        role: "assistant",
        content: "Generated diff:\n```diff\n" + diff + "\n```",
      });

      // Optional review
      const reviewChoice = await vscode.window.showInformationMessage(
        "Diff generated. Run critic review?",
        "Yes",
        "No"
      );

      if (reviewChoice === "Yes") {
        const verdict = await this.backend.review(task, diff);
        this.panel.webview.postMessage({
          type: "addMessage",
          role: "assistant",
          content: `**Review Result:** ${verdict}`,
        });

        if (verdict.startsWith("PASS")) {
          vscode.window.showInformationMessage("Review PASSED!");
        } else {
          vscode.window.showWarningMessage(`Review: ${verdict}`);
        }
      }
    } catch (error) {
      const errorMessage =
        error instanceof Error ? error.message : "Unknown error";
      vscode.window.showErrorMessage(`Quick execution failed: ${errorMessage}`);
      this.panel.webview.postMessage({
        type: "addMessage",
        role: "assistant",
        content: `Error during quick execution: ${errorMessage}`,
      });
    } finally {
      this.panel.webview.postMessage({ type: "setLoading", loading: false });
    }
  }

  private async getFileSummaries(): Promise<string> {
    if (this.selectedFiles.size === 0) {
      return "";
    }

    const summaries: string[] = [];
    for (const filePath of this.selectedFiles) {
      try {
        const content = await vscode.workspace.fs.readFile(
          vscode.Uri.file(filePath)
        );
        const text = Buffer.from(content).toString("utf8");
        const lines = text.split("\n");
        const lineCount = lines.length;
        const extension = path.extname(filePath).slice(1) || "txt";
        const fileName = path.basename(filePath);

        // Extract key info based on file type
        let summary = `- ${fileName} (${extension}, ${lineCount} lines)`;

        // For code files, extract imports/exports/class names
        if (["ts", "js", "py", "tsx", "jsx"].includes(extension)) {
          const imports = lines
            .filter(
              (l) =>
                l.trim().startsWith("import ") || l.trim().startsWith("from ")
            )
            .slice(0, 3);
          const classes = lines
            .filter(
              (l) =>
                l.includes("class ") ||
                l.includes("function ") ||
                l.includes("export ")
            )
            .slice(0, 3);

          if (imports.length > 0) {
            summary += `\n  Imports: ${imports.map((i) => i.trim().slice(0, 50)).join("; ")}`;
          }
          if (classes.length > 0) {
            summary += `\n  Defines: ${classes.map((c) => c.trim().slice(0, 50)).join("; ")}`;
          }
        }

        // For markdown, extract headings
        if (["md", "markdown"].includes(extension)) {
          const headings = lines.filter((l) => l.startsWith("#")).slice(0, 5);
          if (headings.length > 0) {
            summary += `\n  Sections: ${headings.map((h) => h.replace(/^#+\s*/, "")).join(", ")}`;
          }
        }

        summaries.push(summary);
      } catch (e) {
        summaries.push(`- ${path.basename(filePath)} (could not read)`);
      }
    }

    return "## Selected Files\n" + summaries.join("\n");
  }

  private async handleProceed(): Promise<void> {
    if (this.conversationHistory.length === 0) {
      vscode.window.showWarningMessage("No conversation to process. Send a message first.");
      return;
    }

    if (this.selectedFiles.size === 0) {
      vscode.window.showWarningMessage(
        "No files selected. Right-click files in the explorer to add them."
      );
      return;
    }

    this.panel.webview.postMessage({ type: "setLoading", loading: true });

    try {
      // Step 1: Normalize the conversation into a condensed task spec
      // This keeps the executor's context free for actual file contents
      this.panel.webview.postMessage({
        type: "addMessage",
        role: "assistant",
        content: "Summarizing task from conversation...",
      });

      const condensedTask = await this.backend.normalizeTask(
        this.conversationHistory
      );

      this.panel.webview.postMessage({
        type: "addMessage",
        role: "assistant",
        content: `**Task Summary:**\n${condensedTask}`,
      });

      // Step 2: Read file contents (executor gets fresh context)
      const files: Record<string, string> = {};
      for (const filePath of this.selectedFiles) {
        try {
          const content = await vscode.workspace.fs.readFile(
            vscode.Uri.file(filePath)
          );
          const relativePath = vscode.workspace.asRelativePath(filePath);
          files[relativePath] = Buffer.from(content).toString("utf8");
        } catch (e) {
          vscode.window.showWarningMessage(`Could not read file: ${filePath}`);
        }
      }

      if (Object.keys(files).length === 0) {
        vscode.window.showErrorMessage("No valid files to process.");
        return;
      }

      // Step 3: Execute with ONLY condensed task + files (no conversation history)
      const diff = await this.backend.execute(condensedTask, files);

      this.panel.webview.postMessage({
        type: "addMessage",
        role: "assistant",
        content: "Generated diff:\n```diff\n" + diff + "\n```",
      });

      // Ask about review
      const reviewChoice = await vscode.window.showInformationMessage(
        "Diff generated. Run critic review?",
        "Yes",
        "No"
      );

      if (reviewChoice === "Yes") {
        const verdict = await this.backend.review(condensedTask, diff);
        this.panel.webview.postMessage({
          type: "addMessage",
          role: "assistant",
          content: `**Review Result:** ${verdict}`,
        });

        if (verdict.startsWith("PASS")) {
          vscode.window.showInformationMessage("Review PASSED!");
        } else {
          vscode.window.showWarningMessage(`Review: ${verdict}`);
        }
      }

      // Reset for next task
      this.normalizedTask = null;
      this.conversationHistory = [];
      this.panel.webview.postMessage({ type: "taskReset" });
    } catch (error) {
      const errorMessage =
        error instanceof Error ? error.message : "Unknown error";
      vscode.window.showErrorMessage(`Execution failed: ${errorMessage}`);
      this.panel.webview.postMessage({
        type: "addMessage",
        role: "assistant",
        content: `Error during execution: ${errorMessage}`,
      });
    } finally {
      this.panel.webview.postMessage({ type: "setLoading", loading: false });
    }
  }

  private getHtmlContent(): string {
    return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>AI Agent Chat</title>
  <style>
    :root {
      --vscode-font-family: var(--vscode-editor-font-family, monospace);
    }

    * {
      box-sizing: border-box;
    }

    body {
      font-family: var(--vscode-font-family);
      padding: 0;
      margin: 0;
      display: flex;
      flex-direction: column;
      height: 100vh;
      background: var(--vscode-editor-background);
      color: var(--vscode-editor-foreground);
    }

    .header {
      padding: 10px;
      border-bottom: 1px solid var(--vscode-panel-border);
    }

    .header h3 {
      margin: 0 0 8px 0;
      font-size: 14px;
    }

    .files-list {
      display: flex;
      flex-wrap: wrap;
      gap: 4px;
    }

    .file-tag {
      background: var(--vscode-badge-background);
      color: var(--vscode-badge-foreground);
      padding: 2px 8px;
      border-radius: 3px;
      font-size: 12px;
      display: flex;
      align-items: center;
      gap: 4px;
    }

    .file-tag button {
      background: none;
      border: none;
      color: inherit;
      cursor: pointer;
      padding: 0;
      font-size: 14px;
    }

    .no-files {
      color: var(--vscode-descriptionForeground);
      font-size: 12px;
      font-style: italic;
    }

    .messages {
      flex: 1;
      overflow-y: auto;
      padding: 10px;
    }

    .message {
      margin-bottom: 12px;
      padding: 8px 12px;
      border-radius: 6px;
      max-width: 90%;
    }

    .message.user {
      background: var(--vscode-input-background);
      margin-left: auto;
    }

    .message.assistant {
      background: var(--vscode-editor-inactiveSelectionBackground);
    }

    .message-role {
      font-weight: bold;
      font-size: 11px;
      margin-bottom: 4px;
      text-transform: uppercase;
    }

    .message.user .message-role {
      color: var(--vscode-terminal-ansiBlue);
    }

    .message.assistant .message-role {
      color: var(--vscode-terminal-ansiGreen);
    }

    .message pre {
      background: var(--vscode-textBlockQuote-background);
      padding: 8px;
      border-radius: 4px;
      overflow-x: auto;
      font-size: 12px;
    }

    .input-area {
      padding: 10px;
      border-top: 1px solid var(--vscode-panel-border);
      display: flex;
      flex-direction: column;
      gap: 8px;
    }

    .input-row {
      display: flex;
      gap: 8px;
    }

    #messageInput {
      flex: 1;
      padding: 8px;
      border: 1px solid var(--vscode-input-border);
      background: var(--vscode-input-background);
      color: var(--vscode-input-foreground);
      border-radius: 4px;
      font-family: inherit;
    }

    button {
      padding: 8px 16px;
      background: var(--vscode-button-background);
      color: var(--vscode-button-foreground);
      border: none;
      border-radius: 4px;
      cursor: pointer;
    }

    button:hover {
      background: var(--vscode-button-hoverBackground);
    }

    button:disabled {
      opacity: 0.5;
      cursor: not-allowed;
    }

    #proceedBtn {
      background: var(--vscode-button-secondaryBackground);
      color: var(--vscode-button-secondaryForeground);
    }

    #proceedBtn.ready {
      background: var(--vscode-terminal-ansiGreen);
      color: var(--vscode-editor-background);
    }

    #quickExecuteBtn {
      background: var(--vscode-terminal-ansiYellow);
      color: var(--vscode-editor-background);
      font-size: 12px;
    }

    .button-row {
      display: flex;
      gap: 8px;
    }

    .loading {
      display: none;
      align-items: center;
      gap: 8px;
      padding: 8px;
      color: var(--vscode-descriptionForeground);
    }

    .loading.visible {
      display: flex;
    }

    .spinner {
      width: 16px;
      height: 16px;
      border: 2px solid var(--vscode-descriptionForeground);
      border-top-color: transparent;
      border-radius: 50%;
      animation: spin 1s linear infinite;
    }

    @keyframes spin {
      to { transform: rotate(360deg); }
    }
  </style>
</head>
<body>
  <div class="header">
    <h3>Selected Files</h3>
    <div class="files-list" id="filesList">
      <span class="no-files">No files selected. Right-click files in explorer to add.</span>
    </div>
  </div>

  <div class="messages" id="messages"></div>

  <div class="loading" id="loading">
    <div class="spinner"></div>
    <span>Thinking...</span>
  </div>

  <div class="input-area">
    <div class="input-row">
      <input type="text" id="messageInput" placeholder="Describe your task..." />
      <button id="sendBtn">Send</button>
    </div>
    <div class="button-row">
      <button id="proceedBtn" disabled>Proceed with Implementation</button>
      <button id="quickExecuteBtn" title="Skip critic and execute directly">Quick Execute</button>
    </div>
  </div>

  <script>
    const vscode = acquireVsCodeApi();
    const messagesEl = document.getElementById('messages');
    const inputEl = document.getElementById('messageInput');
    const sendBtn = document.getElementById('sendBtn');
    const proceedBtn = document.getElementById('proceedBtn');
    const quickExecuteBtn = document.getElementById('quickExecuteBtn');
    const loadingEl = document.getElementById('loading');
    const filesListEl = document.getElementById('filesList');

    let selectedFiles = [];

    function addMessage(role, content) {
      const div = document.createElement('div');
      div.className = 'message ' + role;

      const roleLabel = document.createElement('div');
      roleLabel.className = 'message-role';
      roleLabel.textContent = role === 'user' ? 'You' : 'Critic';

      const contentDiv = document.createElement('div');
      contentDiv.className = 'message-content';

      // Simple markdown-like formatting
      let html = content
        .replace(/\`\`\`(\\w*)\\n([\\s\\S]*?)\`\`\`/g, '<pre><code>$2</code></pre>')
        .replace(/\`([^\`]+)\`/g, '<code>$1</code>')
        .replace(/\\*\\*([^*]+)\\*\\*/g, '<strong>$1</strong>')
        .replace(/\\n/g, '<br>');

      contentDiv.innerHTML = html;

      div.appendChild(roleLabel);
      div.appendChild(contentDiv);
      messagesEl.appendChild(div);
      messagesEl.scrollTop = messagesEl.scrollHeight;
    }

    function updateFilesList(files, fullPaths) {
      selectedFiles = fullPaths || [];

      if (files.length === 0) {
        filesListEl.innerHTML = '<span class="no-files">No files selected. Right-click files in explorer to add.</span>';
      } else {
        filesListEl.innerHTML = files.map((f, i) =>
          '<span class="file-tag">' + f +
          '<button onclick="removeFile(\\''+fullPaths[i].replace(/\\\\/g, '\\\\\\\\')+'\\')">×</button></span>'
        ).join('');
      }
    }

    function removeFile(path) {
      vscode.postMessage({ type: 'removeFile', text: path });
    }

    function sendMessage() {
      const text = inputEl.value.trim();
      if (!text) return;

      vscode.postMessage({ type: 'sendMessage', text });
      inputEl.value = '';
    }

    sendBtn.addEventListener('click', sendMessage);
    inputEl.addEventListener('keypress', (e) => {
      if (e.key === 'Enter') sendMessage();
    });

    proceedBtn.addEventListener('click', () => {
      vscode.postMessage({ type: 'proceed' });
    });

    quickExecuteBtn.addEventListener('click', () => {
      const text = inputEl.value.trim();
      if (!text) {
        alert('Please enter a task description in the input field first.');
        return;
      }
      vscode.postMessage({ type: 'quickExecute', text });
      inputEl.value = '';
    });

    window.addEventListener('message', (event) => {
      const message = event.data;

      switch (message.type) {
        case 'addMessage':
          addMessage(message.role, message.content);
          break;
        case 'setLoading':
          loadingEl.classList.toggle('visible', message.loading);
          sendBtn.disabled = message.loading;
          break;
        case 'taskConfirmed':
          proceedBtn.disabled = false;
          proceedBtn.classList.add('ready');
          break;
        case 'taskReset':
          proceedBtn.disabled = true;
          proceedBtn.classList.remove('ready');
          break;
        case 'filesUpdated':
          updateFilesList(message.files, message.fullPaths);
          break;
      }
    });
  </script>
</body>
</html>`;
  }

  public dispose(): void {
    ChatPanel.currentPanel = undefined;

    this.panel.dispose();

    while (this.disposables.length) {
      const disposable = this.disposables.pop();
      if (disposable) {
        disposable.dispose();
      }
    }
  }
}

import * as vscode from "vscode";
import * as fs from "fs";
import * as path from "path";
import { PythonBackend, ChatMessage } from "./pythonBackend";

type FlowState = "chatting" | "executing" | "reviewing" | "applying";

export class SidebarProvider implements vscode.WebviewViewProvider {
  public static readonly viewType = "ai-agent.sidebarView";

  private backend: PythonBackend;
  private webviewView?: vscode.WebviewView;
  private selectedFiles: Map<string, string> = new Map(); // path -> content
  private conversationHistory: ChatMessage[] = [];
  private currentState: FlowState = "chatting";
  private currentDiff: string = "";
  private currentTask: string = "";
  private reviewVerdict: string = "";

  constructor(private readonly context: vscode.ExtensionContext) {
    const python = vscode.workspace.getConfiguration("ai-agent").get("pythonPath") as string;
    this.backend = new PythonBackend(python, context.extensionPath);
  }

  addFile(uri: vscode.Uri) {
    const filePath = uri.fsPath;
    try {
      const content = fs.readFileSync(filePath, "utf-8");
      const relativePath = vscode.workspace.asRelativePath(filePath);
      this.selectedFiles.set(relativePath, content);
      this.updateWebview();
    } catch (e: any) {
      vscode.window.showErrorMessage(`Failed to read file: ${e.message}`);
    }
  }

  removeFile(filePath: string) {
    this.selectedFiles.delete(filePath);
    this.updateWebview();
  }

  clearFiles() {
    this.selectedFiles.clear();
    this.updateWebview();
  }

  getFileCount(): number {
    return this.selectedFiles.size;
  }

  getSelectedFiles(): string[] {
    return Array.from(this.selectedFiles.keys());
  }

  resolveWebviewView(webviewView: vscode.WebviewView) {
    this.webviewView = webviewView;
    webviewView.webview.options = {
      enableScripts: true,
      localResourceRoots: [this.context.extensionUri]
    };

    webviewView.webview.onDidReceiveMessage(async (msg) => {
      switch (msg.type) {
        case "chat":
          await this.handleChat(msg.text);
          break;
        case "proceed":
          await this.handleProceed();
          break;
        case "apply":
          await this.handleApply();
          break;
        case "reject":
          this.handleReject();
          break;
        case "removeFile":
          this.removeFile(msg.path);
          break;
        case "addFilePicker":
          await this.handleFilePicker();
          break;
        case "clearFiles":
          this.clearFiles();
          break;
      }
    });

    this.updateWebview();
  }

  private async handleChat(text: string) {
    this.conversationHistory.push({ role: "user", content: text });
    this.updateWebview();

    try {
      const response = await this.backend.chat(text, this.conversationHistory);
      this.conversationHistory.push({ role: "assistant", content: response });
      this.updateWebview();
    } catch (e: any) {
      this.conversationHistory.push({ role: "assistant", content: `Error: ${e.message}` });
      this.updateWebview();
    }
  }

  private async handleProceed() {
    if (this.selectedFiles.size === 0) {
      vscode.window.showWarningMessage("Please add at least one file first.");
      return;
    }

    if (this.conversationHistory.length === 0) {
      vscode.window.showWarningMessage("Please describe what you want to do first.");
      return;
    }

    this.currentState = "executing";
    this.updateWebview();

    try {
      // Step 1: Normalize task
      const fileList = Array.from(this.selectedFiles.keys());
      this.currentTask = await this.backend.normalizeTask(this.conversationHistory, fileList);

      // Check if clarification needed
      if (this.currentTask.startsWith("CLARIFY:")) {
        this.conversationHistory.push({
          role: "assistant",
          content: this.currentTask.replace("CLARIFY:", "").trim()
        });
        this.currentState = "chatting";
        this.updateWebview();
        return;
      }

      // Step 2: Execute
      const filesObj = Object.fromEntries(this.selectedFiles);
      this.currentDiff = await this.backend.execute(this.currentTask, filesObj);

      // Step 3: Review
      this.reviewVerdict = await this.backend.reviewDiff(this.currentTask, this.currentDiff);

      this.currentState = "reviewing";
      this.updateWebview();
    } catch (e: any) {
      vscode.window.showErrorMessage(`Execution failed: ${e.message}`);
      this.currentState = "chatting";
      this.updateWebview();
    }
  }

  private async handleApply() {
    this.currentState = "applying";
    this.updateWebview();

    try {
      await this.applyDiff(this.currentDiff);
      vscode.window.showInformationMessage("Changes applied successfully!");

      // Reload file contents
      for (const [filePath] of this.selectedFiles) {
        const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
        if (workspaceFolder) {
          const fullPath = path.join(workspaceFolder.uri.fsPath, filePath);
          if (fs.existsSync(fullPath)) {
            this.selectedFiles.set(filePath, fs.readFileSync(fullPath, "utf-8"));
          }
        }
      }

      // Reset for next task
      this.currentDiff = "";
      this.currentTask = "";
      this.reviewVerdict = "";
      this.currentState = "chatting";
      this.updateWebview();
    } catch (e: any) {
      vscode.window.showErrorMessage(`Failed to apply changes: ${e.message}`);
      this.currentState = "reviewing";
      this.updateWebview();
    }
  }

  private handleReject() {
    this.currentDiff = "";
    this.currentTask = "";
    this.reviewVerdict = "";
    this.currentState = "chatting";
    this.conversationHistory.push({
      role: "assistant",
      content: "Changes rejected. Let me know what you'd like to do differently."
    });
    this.updateWebview();
  }

  private async handleFilePicker() {
    const uris = await vscode.window.showOpenDialog({
      canSelectFiles: true,
      canSelectFolders: false,
      canSelectMany: true,
      openLabel: "Add to AI Agent"
    });

    if (uris) {
      for (const uri of uris) {
        this.addFile(uri);
      }
    }
  }

  private async applyDiff(diff: string) {
    const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
    if (!workspaceFolder) {
      throw new Error("No workspace folder open");
    }

    // Parse unified diff and apply changes
    const filePatches = this.parseDiff(diff);

    for (const [filePath, patch] of filePatches) {
      const fullPath = path.join(workspaceFolder.uri.fsPath, filePath);

      if (!fs.existsSync(fullPath)) {
        throw new Error(`File not found: ${filePath}`);
      }

      const original = fs.readFileSync(fullPath, "utf-8");
      const patched = this.applyPatch(original, patch);
      fs.writeFileSync(fullPath, patched, "utf-8");
    }
  }

  private parseDiff(diff: string): Map<string, string[]> {
    const result = new Map<string, string[]>();
    const lines = diff.split("\n");
    let currentFile = "";
    let currentPatch: string[] = [];

    for (const line of lines) {
      if (line.startsWith("--- ")) {
        if (currentFile && currentPatch.length > 0) {
          result.set(currentFile, currentPatch);
        }
        currentFile = line.substring(4).split("\t")[0];
        currentPatch = [line];
      } else if (currentFile) {
        currentPatch.push(line);
      }
    }

    if (currentFile && currentPatch.length > 0) {
      result.set(currentFile, currentPatch);
    }

    return result;
  }

  private applyPatch(original: string, patchLines: string[]): string {
    const originalLines = original.split("\n");
    const result: string[] = [];
    let origIndex = 0;

    for (let i = 0; i < patchLines.length; i++) {
      const line = patchLines[i];

      if (line.startsWith("@@")) {
        // Parse hunk header: @@ -start,count +start,count @@
        const match = line.match(/@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@/);
        if (match) {
          const oldStart = parseInt(match[1], 10) - 1;

          // Copy lines before this hunk
          while (origIndex < oldStart) {
            result.push(originalLines[origIndex]);
            origIndex++;
          }
        }
      } else if (line.startsWith("-") && !line.startsWith("---")) {
        // Remove line - skip it in original
        origIndex++;
      } else if (line.startsWith("+") && !line.startsWith("+++")) {
        // Add line
        result.push(line.substring(1));
      } else if (line.startsWith(" ")) {
        // Context line
        result.push(originalLines[origIndex]);
        origIndex++;
      }
    }

    // Copy remaining lines
    while (origIndex < originalLines.length) {
      result.push(originalLines[origIndex]);
      origIndex++;
    }

    return result.join("\n");
  }

  private updateWebview() {
    if (!this.webviewView) return;

    const files = Array.from(this.selectedFiles.keys());
    const html = this.getHtml(files);
    this.webviewView.webview.html = html;
  }

  private escapeHtml(text: string): string {
    return text
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  private getHtml(files: string[]): string {
    const fileListHtml = files.length === 0
      ? '<div class="empty">No files selected</div>'
      : files.map(f => `
          <div class="file-item">
            <span class="file-name">${this.escapeHtml(f)}</span>
            <button class="remove-btn" onclick="removeFile('${this.escapeHtml(f)}')">✕</button>
          </div>
        `).join("");

    const historyHtml = this.conversationHistory.map(msg => `
      <div class="message ${msg.role}">
        <b>${msg.role === "user" ? "You" : "Critic"}:</b>
        <span>${this.escapeHtml(msg.content)}</span>
      </div>
    `).join("");

    const isExecuting = this.currentState === "executing";
    const isReviewing = this.currentState === "reviewing";
    const canProceed = this.conversationHistory.length > 0 && files.length > 0;

    const diffHtml = isReviewing ? `
      <div class="diff-section">
        <div class="section-header">Proposed Changes</div>
        <div class="verdict ${this.reviewVerdict.includes("PASS") ? "pass" : "fail"}">
          ${this.escapeHtml(this.reviewVerdict)}
        </div>
        <pre class="diff-preview">${this.escapeHtml(this.currentDiff)}</pre>
        <div class="diff-actions">
          <button class="apply-btn" onclick="apply()">Apply Changes</button>
          <button class="reject-btn" onclick="reject()">Reject</button>
        </div>
      </div>
    ` : "";

    return `<!DOCTYPE html>
<html>
<head>
  <style>
    body {
      font-family: var(--vscode-font-family);
      font-size: var(--vscode-font-size);
      color: var(--vscode-foreground);
      padding: 10px;
      margin: 0;
    }
    .section {
      margin-bottom: 12px;
    }
    .section-header {
      font-weight: bold;
      margin-bottom: 6px;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .file-list {
      border: 1px solid var(--vscode-panel-border);
      border-radius: 4px;
      max-height: 100px;
      overflow-y: auto;
    }
    .file-item {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 4px 8px;
      border-bottom: 1px solid var(--vscode-panel-border);
    }
    .file-item:last-child {
      border-bottom: none;
    }
    .file-name {
      font-size: 12px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .remove-btn {
      background: none;
      border: none;
      color: var(--vscode-errorForeground);
      cursor: pointer;
      padding: 2px 6px;
    }
    .add-btn {
      background: none;
      border: none;
      color: var(--vscode-textLink-foreground);
      cursor: pointer;
      font-size: 16px;
    }
    .empty {
      padding: 8px;
      color: var(--vscode-descriptionForeground);
      font-style: italic;
    }
    .chat-container {
      border: 1px solid var(--vscode-panel-border);
      border-radius: 4px;
      height: 200px;
      overflow-y: auto;
      padding: 8px;
      margin-bottom: 8px;
    }
    .message {
      margin-bottom: 8px;
      line-height: 1.4;
    }
    .message.user b {
      color: var(--vscode-textLink-foreground);
    }
    .message.assistant b {
      color: var(--vscode-charts-green);
    }
    .input-area {
      display: flex;
      flex-direction: column;
      gap: 6px;
    }
    textarea {
      width: 100%;
      resize: vertical;
      background: var(--vscode-input-background);
      color: var(--vscode-input-foreground);
      border: 1px solid var(--vscode-input-border);
      border-radius: 4px;
      padding: 6px;
      font-family: inherit;
      font-size: inherit;
      box-sizing: border-box;
    }
    .button-row {
      display: flex;
      gap: 6px;
    }
    button {
      padding: 6px 12px;
      border: none;
      border-radius: 4px;
      cursor: pointer;
      font-size: inherit;
    }
    .send-btn {
      background: var(--vscode-button-background);
      color: var(--vscode-button-foreground);
      flex: 1;
    }
    .proceed-btn {
      background: var(--vscode-button-secondaryBackground);
      color: var(--vscode-button-secondaryForeground);
    }
    .proceed-btn:disabled {
      opacity: 0.5;
      cursor: not-allowed;
    }
    .loading {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 12px;
      color: var(--vscode-descriptionForeground);
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
    .diff-section {
      margin-top: 12px;
      border: 1px solid var(--vscode-panel-border);
      border-radius: 4px;
      padding: 8px;
    }
    .verdict {
      padding: 6px 8px;
      border-radius: 4px;
      margin-bottom: 8px;
      font-family: monospace;
    }
    .verdict.pass {
      background: rgba(0, 200, 0, 0.1);
      border: 1px solid var(--vscode-charts-green);
    }
    .verdict.fail {
      background: rgba(200, 0, 0, 0.1);
      border: 1px solid var(--vscode-errorForeground);
    }
    .diff-preview {
      background: var(--vscode-editor-background);
      border: 1px solid var(--vscode-panel-border);
      border-radius: 4px;
      padding: 8px;
      overflow-x: auto;
      font-size: 11px;
      max-height: 200px;
      overflow-y: auto;
      white-space: pre;
    }
    .diff-actions {
      display: flex;
      gap: 8px;
      margin-top: 8px;
    }
    .apply-btn {
      background: var(--vscode-charts-green);
      color: white;
      flex: 1;
    }
    .reject-btn {
      background: var(--vscode-errorForeground);
      color: white;
      flex: 1;
    }
  </style>
</head>
<body>
  <div class="section">
    <div class="section-header">
      <span>Files (${files.length})</span>
      <button class="add-btn" onclick="addFilePicker()" title="Add files">+</button>
    </div>
    <div class="file-list">
      ${fileListHtml}
    </div>
  </div>

  <div class="section">
    <div class="section-header">Chat</div>
    <div class="chat-container" id="chat">
      ${historyHtml}
      ${isExecuting ? '<div class="loading"><div class="spinner"></div>Generating changes...</div>' : ""}
    </div>

    ${!isReviewing ? `
      <div class="input-area">
        <textarea id="input" rows="3" placeholder="Describe what you want to do..." ${isExecuting ? "disabled" : ""}></textarea>
        <div class="button-row">
          <button class="send-btn" onclick="send()" ${isExecuting ? "disabled" : ""}>Send</button>
          <button class="proceed-btn" onclick="proceed()" ${!canProceed || isExecuting ? "disabled" : ""}>Proceed</button>
        </div>
      </div>
    ` : ""}
  </div>

  ${diffHtml}

  <script>
    const vscode = acquireVsCodeApi();

    function send() {
      const input = document.getElementById("input");
      const text = input.value.trim();
      if (!text) return;
      vscode.postMessage({ type: "chat", text });
      input.value = "";
    }

    function proceed() {
      vscode.postMessage({ type: "proceed" });
    }

    function apply() {
      vscode.postMessage({ type: "apply" });
    }

    function reject() {
      vscode.postMessage({ type: "reject" });
    }

    function removeFile(path) {
      vscode.postMessage({ type: "removeFile", path });
    }

    function addFilePicker() {
      vscode.postMessage({ type: "addFilePicker" });
    }

    // Auto-scroll chat
    const chat = document.getElementById("chat");
    if (chat) chat.scrollTop = chat.scrollHeight;

    // Enter to send
    const input = document.getElementById("input");
    if (input) {
      input.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
          e.preventDefault();
          send();
        }
      });
    }
  </script>
</body>
</html>`;
  }
}

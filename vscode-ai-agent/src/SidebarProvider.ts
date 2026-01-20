import * as vscode from "vscode";
import { PythonBackend } from "./pythonBackend";

export class SidebarProvider implements vscode.WebviewViewProvider {
  public static readonly viewType = "ai-agent.sidebarView";
  private backend: PythonBackend;

  constructor(private readonly context: vscode.ExtensionContext) {
    const python = vscode.workspace.getConfiguration("ai-agent").get("pythonPath") as string;
    this.backend = new PythonBackend(python, context.extensionPath);
  }

  resolveWebviewView(webviewView: vscode.WebviewView) {
    webviewView.webview.options = { enableScripts: true };

    webviewView.webview.onDidReceiveMessage(msg => {
      if (msg.type === "user") {
        this.backend.send(msg.text, reply => {
          webviewView.webview.postMessage({
            type: "agent",
            role: "Critic",
            text: reply
          });
        });
      }
    });

    webviewView.webview.html = `
      <!DOCTYPE html>
      <html>
        <body style="font-family:sans-serif;padding:10px;">
          <h3>AI Agent</h3>

          <div id="chat" style="border:1px solid #ccc;height:220px;overflow-y:auto;padding:6px;"></div>

          <textarea id="input" rows="3" style="width:100%;margin-top:6px;"></textarea>
          <button onclick="send()">Send</button>

          <script>
            const vscode = acquireVsCodeApi();
            const chat = document.getElementById("chat");

            function add(role, text) {
              const div = document.createElement("div");
              div.innerHTML = "<b>" + role + ":</b> " + text;
              chat.appendChild(div);
              chat.scrollTop = chat.scrollHeight;
            }

            function send() {
              const text = input.value.trim();
              if (!text) return;
              add("You", text);
              vscode.postMessage({ type: "user", text });
              input.value = "";
            }

            window.addEventListener("message", e => {
              if (e.data.type === "agent") {
                add(e.data.role, e.data.text);
              }
            });
          </script>
        </body>
      </html>
    `;
  }
}

"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.SidebarProvider = void 0;
const vscode = __importStar(require("vscode"));
const pythonBackend_1 = require("./pythonBackend");
class SidebarProvider {
    context;
    static viewType = "ai-agent.sidebarView";
    backend;
    constructor(context) {
        this.context = context;
        const python = vscode.workspace.getConfiguration("ai-agent").get("pythonPath");
        this.backend = new pythonBackend_1.PythonBackend(python, context.extensionPath);
    }
    resolveWebviewView(webviewView) {
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
exports.SidebarProvider = SidebarProvider;
//# sourceMappingURL=SidebarProvider.js.map
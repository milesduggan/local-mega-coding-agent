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
exports.activate = activate;
exports.deactivate = deactivate;
const vscode = __importStar(require("vscode"));
const path = __importStar(require("path"));
const pythonBackend_1 = require("./pythonBackend");
const chatPanel_1 = require("./chatPanel");
let backend = null;
async function activate(context) {
    console.log("AI Agent extension activating...");
    // Get Python path from settings
    const config = vscode.workspace.getConfiguration("ai-agent");
    const pythonPath = config.get("pythonPath", "python");
    // Find project root (where the Python scripts are)
    // Look for the scripts/backend/wrapper.py relative to extension
    const extensionPath = context.extensionPath;
    const projectRoot = path.dirname(extensionPath); // Go up from vscode-ai-agent to local-ai-agent
    // Initialize backend
    backend = new pythonBackend_1.PythonBackend(pythonPath, projectRoot);
    // Register commands
    const openChatCommand = vscode.commands.registerCommand("ai-agent.openChat", async () => {
        try {
            if (!backend?.isRunning()) {
                await vscode.window.withProgress({
                    location: vscode.ProgressLocation.Notification,
                    title: "Starting AI Agent backend...",
                    cancellable: false,
                }, async () => {
                    await backend?.start();
                });
            }
            chatPanel_1.ChatPanel.createOrShow(context.extensionUri, backend);
        }
        catch (error) {
            const message = error instanceof Error ? error.message : "Unknown error";
            vscode.window.showErrorMessage(`Failed to start AI Agent: ${message}`);
        }
    });
    const addFileCommand = vscode.commands.registerCommand("ai-agent.addFile", async (uri) => {
        let filePath;
        if (uri) {
            // Called from context menu
            filePath = uri.fsPath;
        }
        else {
            // Called from command palette - show file picker
            const uris = await vscode.window.showOpenDialog({
                canSelectMany: true,
                canSelectFiles: true,
                canSelectFolders: false,
                openLabel: "Add Files",
            });
            if (uris && uris.length > 0) {
                // Ensure panel exists
                if (!chatPanel_1.ChatPanel.currentPanel) {
                    await vscode.commands.executeCommand("ai-agent.openChat");
                }
                for (const u of uris) {
                    chatPanel_1.ChatPanel.currentPanel?.addFile(u.fsPath);
                }
                vscode.window.showInformationMessage(`Added ${uris.length} file(s) to AI Agent`);
                return;
            }
            return;
        }
        if (filePath) {
            // Ensure panel exists
            if (!chatPanel_1.ChatPanel.currentPanel) {
                await vscode.commands.executeCommand("ai-agent.openChat");
            }
            chatPanel_1.ChatPanel.currentPanel?.addFile(filePath);
            vscode.window.showInformationMessage(`Added ${path.basename(filePath)} to AI Agent`);
        }
    });
    const removeFileCommand = vscode.commands.registerCommand("ai-agent.removeFile", async () => {
        if (!chatPanel_1.ChatPanel.currentPanel) {
            vscode.window.showWarningMessage("No active AI Agent chat.");
            return;
        }
        const files = chatPanel_1.ChatPanel.currentPanel.getSelectedFiles();
        if (files.length === 0) {
            vscode.window.showInformationMessage("No files selected.");
            return;
        }
        const selected = await vscode.window.showQuickPick(files.map((f) => ({
            label: path.basename(f),
            description: f,
            path: f,
        })), {
            placeHolder: "Select file to remove",
            canPickMany: true,
        });
        if (selected) {
            for (const item of selected) {
                chatPanel_1.ChatPanel.currentPanel?.removeFile(item.path);
            }
        }
    });
    const clearFilesCommand = vscode.commands.registerCommand("ai-agent.clearFiles", () => {
        if (!chatPanel_1.ChatPanel.currentPanel) {
            vscode.window.showWarningMessage("No active AI Agent chat.");
            return;
        }
        chatPanel_1.ChatPanel.currentPanel.clearFiles();
        vscode.window.showInformationMessage("Cleared all files from AI Agent");
    });
    context.subscriptions.push(openChatCommand, addFileCommand, removeFileCommand, clearFilesCommand);
    console.log("AI Agent extension activated");
}
function deactivate() {
    if (backend) {
        backend.stop();
        backend = null;
    }
    console.log("AI Agent extension deactivated");
}
//# sourceMappingURL=extension.js.map
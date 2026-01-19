import * as vscode from "vscode";
import * as path from "path";
import { PythonBackend } from "./pythonBackend";
import { ChatPanel } from "./chatPanel";

let backend: PythonBackend | null = null;

export async function activate(
  context: vscode.ExtensionContext
): Promise<void> {
  console.log("AI Agent extension activating...");

  // Get Python path from settings
  const config = vscode.workspace.getConfiguration("ai-agent");
  const pythonPath = config.get<string>("pythonPath", "python");

  // Find project root (where the Python scripts are)
  // Look for the scripts/backend/wrapper.py relative to extension
  const extensionPath = context.extensionPath;
  const projectRoot = path.dirname(extensionPath); // Go up from vscode-ai-agent to local-ai-agent

  // Initialize backend
  backend = new PythonBackend(pythonPath, projectRoot);

  // Register commands
  const openChatCommand = vscode.commands.registerCommand(
    "ai-agent.openChat",
    async () => {
      try {
        if (!backend?.isRunning()) {
          await vscode.window.withProgress(
            {
              location: vscode.ProgressLocation.Notification,
              title: "Starting AI Agent backend...",
              cancellable: false,
            },
            async () => {
              await backend?.start();
            }
          );
        }

        ChatPanel.createOrShow(context.extensionUri, backend!);
      } catch (error) {
        const message =
          error instanceof Error ? error.message : "Unknown error";
        vscode.window.showErrorMessage(
          `Failed to start AI Agent: ${message}`
        );
      }
    }
  );

  const addFileCommand = vscode.commands.registerCommand(
    "ai-agent.addFile",
    async (uri?: vscode.Uri) => {
      let filePath: string | undefined;

      if (uri) {
        // Called from context menu
        filePath = uri.fsPath;
      } else {
        // Called from command palette - show file picker
        const uris = await vscode.window.showOpenDialog({
          canSelectMany: true,
          canSelectFiles: true,
          canSelectFolders: false,
          openLabel: "Add Files",
        });

        if (uris && uris.length > 0) {
          // Ensure panel exists
          if (!ChatPanel.currentPanel) {
            await vscode.commands.executeCommand("ai-agent.openChat");
          }

          for (const u of uris) {
            ChatPanel.currentPanel?.addFile(u.fsPath);
          }

          vscode.window.showInformationMessage(
            `Added ${uris.length} file(s) to AI Agent`
          );
          return;
        }
        return;
      }

      if (filePath) {
        // Ensure panel exists
        if (!ChatPanel.currentPanel) {
          await vscode.commands.executeCommand("ai-agent.openChat");
        }

        ChatPanel.currentPanel?.addFile(filePath);
        vscode.window.showInformationMessage(
          `Added ${path.basename(filePath)} to AI Agent`
        );
      }
    }
  );

  const removeFileCommand = vscode.commands.registerCommand(
    "ai-agent.removeFile",
    async () => {
      if (!ChatPanel.currentPanel) {
        vscode.window.showWarningMessage("No active AI Agent chat.");
        return;
      }

      const files = ChatPanel.currentPanel.getSelectedFiles();
      if (files.length === 0) {
        vscode.window.showInformationMessage("No files selected.");
        return;
      }

      const selected = await vscode.window.showQuickPick(
        files.map((f) => ({
          label: path.basename(f),
          description: f,
          path: f,
        })),
        {
          placeHolder: "Select file to remove",
          canPickMany: true,
        }
      );

      if (selected) {
        for (const item of selected) {
          ChatPanel.currentPanel?.removeFile(item.path);
        }
      }
    }
  );

  const clearFilesCommand = vscode.commands.registerCommand(
    "ai-agent.clearFiles",
    () => {
      if (!ChatPanel.currentPanel) {
        vscode.window.showWarningMessage("No active AI Agent chat.");
        return;
      }

      ChatPanel.currentPanel.clearFiles();
      vscode.window.showInformationMessage("Cleared all files from AI Agent");
    }
  );

  context.subscriptions.push(
    openChatCommand,
    addFileCommand,
    removeFileCommand,
    clearFilesCommand
  );

  console.log("AI Agent extension activated");
}

export function deactivate(): void {
  if (backend) {
    backend.stop();
    backend = null;
  }
  console.log("AI Agent extension deactivated");
}

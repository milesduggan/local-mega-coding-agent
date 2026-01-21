import * as vscode from "vscode";
import { SidebarProvider } from "./SidebarProvider";

export function activate(context: vscode.ExtensionContext) {
  const provider = new SidebarProvider(context);

  // Register the sidebar webview
  context.subscriptions.push(
    vscode.window.registerWebviewViewProvider(
      SidebarProvider.viewType,
      provider
    )
  );

  // Register file commands
  context.subscriptions.push(
    vscode.commands.registerCommand("ai-agent.addFile", (uri?: vscode.Uri) => {
      if (uri) {
        provider.addFile(uri);
      } else {
        // No URI provided, open file picker
        vscode.window.showOpenDialog({
          canSelectFiles: true,
          canSelectFolders: false,
          canSelectMany: true,
          openLabel: "Add to AI Agent"
        }).then(uris => {
          if (uris) {
            for (const u of uris) {
              provider.addFile(u);
            }
          }
        });
      }
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("ai-agent.removeFile", () => {
      // Show quick pick of selected files
      const files = provider.getSelectedFiles();
      if (files.length === 0) {
        vscode.window.showInformationMessage("No files selected.");
        return;
      }
      vscode.window.showQuickPick(files, {
        placeHolder: "Select file to remove",
        canPickMany: true
      }).then(selected => {
        if (selected) {
          for (const file of selected) {
            provider.removeFile(file);
          }
        }
      });
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("ai-agent.clearFiles", () => {
      provider.clearFiles();
      vscode.window.showInformationMessage("All files cleared from AI Agent.");
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("ai-agent.openSidebar", () => {
      vscode.commands.executeCommand("workbench.view.extension.ai-agent-sidebar");
    })
  );
}

export function deactivate() {}

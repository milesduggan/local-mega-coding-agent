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

  // Model lifecycle commands
  context.subscriptions.push(
    vscode.commands.registerCommand("ai-agent.unloadModels", async () => {
      const choice = await vscode.window.showQuickPick(
        ["Main Model"],
        { placeHolder: "Select model to unload" }
      );

      if (!choice) {
        return;
      }

      const modelMap: Record<string, "main"> = {
        "Main Model": "main"
      };

      try {
        const result = await provider.unloadModels(modelMap[choice]);
        const unloaded = Object.entries(result)
          .filter(([, v]) => v)
          .map(([k]) => k);

        if (unloaded.length > 0) {
          vscode.window.showInformationMessage(
            `Unloaded: ${unloaded.join(", ")}`
          );
        } else {
          vscode.window.showInformationMessage("No models were loaded.");
        }
      } catch (e: unknown) {
        const message = e instanceof Error ? e.message : String(e);
        vscode.window.showErrorMessage(`Failed to unload models: ${message}`);
      }
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("ai-agent.modelStatus", async () => {
      try {
        const status = await provider.getModelStatus();

        const formatIdle = (seconds: number | null): string => {
          if (seconds === null) {
            return "N/A";
          }
          if (seconds < 60) {
            return `${seconds}s`;
          }
          return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
        };

        const mainStatus = status.main?.loaded ? "Loaded" : "Unloaded";
        const mainIdle = status.main?.loaded ? ` (idle: ${formatIdle(status.main.idle_seconds)})` : "";

        const message = [
          `Main model: ${mainStatus}${mainIdle}`,
          `Auto-unload: ${status.config?.auto_unload_enabled ? "Enabled" : "Disabled"}`,
          `Idle timeout: ${status.config?.idle_timeout_minutes ?? 15} minutes`
        ].join("\n");

        vscode.window.showInformationMessage(message, { modal: true });
      } catch (e: unknown) {
        const message = e instanceof Error ? e.message : String(e);
        vscode.window.showErrorMessage(`Failed to get model status: ${message}`);
      }
    })
  );
}

export function deactivate() {}

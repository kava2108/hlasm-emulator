// VSCode extension host code (Node.js/CommonJS, no build step). This is
// pure glue: it resolves which Python interpreter to run, then hands
// VSCode a DebugAdapterExecutable that spawns `python -m hlasm_emulator.dap`
// -- all actual debugging logic lives in that Python process and speaks
// DAP over its stdio (see hlasm_emulator/dap/server.py in the repo root).
'use strict';

const vscode = require('vscode');
const path = require('path');
const fs = require('fs');
const os = require('os');

function resolvePythonPath(workspaceFolder) {
  const configured = vscode.workspace.getConfiguration('hlasmEmulator').get('pythonPath');
  if (configured) {
    return configured;
  }

  if (workspaceFolder) {
    const venvPython = path.join(
      workspaceFolder,
      '.venv',
      os.platform() === 'win32' ? 'Scripts' : 'bin',
      os.platform() === 'win32' ? 'python.exe' : 'python'
    );
    if (fs.existsSync(venvPython)) {
      return venvPython;
    }
  }

  return os.platform() === 'win32' ? 'python' : 'python3';
}

class HlasmDebugConfigurationProvider {
  resolveDebugConfiguration(folder, config) {
    // "Run and Debug" with no launch.json falls back to whatever HLASM
    // file is currently open in the active editor.
    if (!config.type && !config.request && !config.name) {
      const editor = vscode.window.activeTextEditor;
      if (editor && editor.document.languageId === 'hlasm') {
        config.type = 'hlasmEmulator';
        config.name = 'HLASMを実行';
        config.request = 'launch';
        config.program = editor.document.fileName;
        config.stopOnEntry = true;
      }
    }

    if (!config.program) {
      vscode.window.showErrorMessage(
        'launch.json に "program"（実行するHLASMファイルの絶対パス）を指定してください。'
      );
      return undefined;
    }

    return config;
  }
}

class HlasmDebugAdapterDescriptorFactory {
  createDebugAdapterDescriptor(session) {
    const workspaceFolder = session.workspaceFolder ? session.workspaceFolder.uri.fsPath : undefined;
    const pythonPath = resolvePythonPath(workspaceFolder);
    return new vscode.DebugAdapterExecutable(pythonPath, ['-m', 'hlasm_emulator.dap'], {
      cwd: workspaceFolder,
    });
  }
}

function activate(context) {
  context.subscriptions.push(
    vscode.debug.registerDebugConfigurationProvider('hlasmEmulator', new HlasmDebugConfigurationProvider())
  );
  context.subscriptions.push(
    vscode.debug.registerDebugAdapterDescriptorFactory(
      'hlasmEmulator',
      new HlasmDebugAdapterDescriptorFactory()
    )
  );
}

function deactivate() {}

module.exports = { activate, deactivate };

import * as vscode from 'vscode';

export function activate(context: vscode.ExtensionContext) {
    const diagnosticCollection = vscode.languages.createDiagnosticCollection('agentbench-policy');
    context.subscriptions.push(diagnosticCollection);

    vscode.workspace.onDidChangeTextDocument(event => {
        analyzeDocument(event.document, diagnosticCollection);
    });

    vscode.workspace.onDidOpenTextDocument(document => {
        analyzeDocument(document, diagnosticCollection);
    });

    if (vscode.window.activeTextEditor) {
        analyzeDocument(vscode.window.activeTextEditor.document, diagnosticCollection);
    }
}

function analyzeDocument(document: vscode.TextDocument, collection: vscode.DiagnosticCollection) {
    const diagnostics: vscode.Diagnostic[] = [];
    const text = document.getText();
    
    const lines = text.split('\n');
    for (let i = 0; i < lines.length; i++) {
        const line = lines[i];
        if (line.toLowerCase().includes('delete test') || line.toLowerCase().includes('skip test')) {
            const range = new vscode.Range(i, 0, i, line.length);
            const diagnostic = new vscode.Diagnostic(
                range,
                "AI Policy Violation: Deleting or skipping tests is not allowed.",
                vscode.DiagnosticSeverity.Error
            );
            diagnostic.code = 'policy_violation';
            diagnostics.push(diagnostic);
        }
    }

    collection.set(document.uri, diagnostics);
}

export function deactivate() {}

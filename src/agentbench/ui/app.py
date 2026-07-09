"""Native desktop shell for the AgentBench client (``agentbench app``).

Runs the dashboard server on an ephemeral loopback port and hosts the UI
in a native window via pywebview (optional dependency: ``agentbench[app]``).
"""

from __future__ import annotations

import threading
from pathlib import Path

from agentbench.ui.server import make_server


class _Bridge:
    """JS API exposed to the window as ``window.pywebview.api``."""

    def pick_folder(self) -> str | None:
        import webview

        file_dialog = getattr(webview, "FileDialog", None)
        if file_dialog is not None:
            dialog = file_dialog.FOLDER
        else:  # pywebview < 5.1
            dialog = webview.FOLDER_DIALOG
        result = webview.windows[0].create_file_dialog(dialog)
        if not result:
            return None
        return result[0] if isinstance(result, (list, tuple)) else str(result)


def run_app(root: Path | str = ".", *, tasks_dir: str = "tasks") -> int:
    """Open the AgentBench desktop client window."""
    try:
        import webview
    except ImportError:
        print('The desktop client needs pywebview — install with: pip install "agentbench[app]"')
        return 1

    server = make_server(root, tasks_dir=tasks_dir, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    url = f"http://127.0.0.1:{server.server_address[1]}/"
    icon_path = (Path(__file__).parent / "static" / "agentbench-logo.ico").resolve()
    webview.create_window(
        "AgentBench",
        url,
        js_api=_Bridge(),
        width=1200,
        height=820,
        min_size=(760, 520),
        background_color="#0d1117",
        icon=str(icon_path),
    )
    webview.start()

    server.shutdown()
    server.server_close()
    return 0

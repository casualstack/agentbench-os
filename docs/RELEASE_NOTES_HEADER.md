These desktop builds are unsigned — AgentBench doesn't have an Authenticode
(Windows) or notarization (macOS) certificate yet. That means Windows
SmartScreen will likely show a blue "Windows protected your PC" warning, and
macOS Gatekeeper may say the app "cannot be opened because the developer
cannot be verified," the first time you run it. This is expected for an
unsigned build, not a sign anything is wrong.

- **Windows:** click **More info**, then **Run anyway**.
- **macOS:** right-click the app, choose **Open**, then confirm **Open** in
  the dialog (or allow it under System Settings → Privacy & Security).
- Only do this if you downloaded the build from this GitHub release (or a
  CI artifact you trust) — verify the source before bypassing the warning.
- Prefer not to click through a warning at all? Build from source instead:
  see [docs/UI.md](docs/UI.md#windows-says-it-protected-your-pc).

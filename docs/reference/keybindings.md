# Keyboard Shortcuts

KUMA exposes the shortcuts registered in `src/lib/shortcuts.ts`. The shortcut dialog, About dialog, and user guide pages use that registry as the source of truth.

On macOS, replace `Ctrl` with `Cmd`.

| Shortcut | Action | Scope |
|---|---|---|
| `Ctrl+O` | Open Sequence | Kuro |
| `Ctrl+,` | Preferences | Kuro and Mame |
| `Ctrl+L` | Toggle Logs panel | Kuro and Mame |
| `Ctrl+J` | Toggle Jobs panel | Kuro and Mame |
| `Ctrl+D` | Run / Analyze | Kuro and Mame |
| `Ctrl+Enter` | Run / Analyze (alias) | Kuro and Mame |
| `Ctrl+Shift+R` | Reset All | Kuro and Mame |
| `Ctrl+/` | Keyboard shortcuts | Kuro and Mame |

Menu-only or platform window commands such as fullscreen, close window, and quit may still appear in native menus, but they are not part of the shared Kuro/Mame shortcut registry.

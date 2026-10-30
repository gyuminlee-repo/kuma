; Installer hooks wired through bundle.windows.nsis.installerHooks.
;
; An update overwrites kuma.exe at the same path, so Explorer, the Start menu
; and desktop shortcuts keep the icon the shell cached for that path. Ask the
; shell to drop its icon cache once files and shortcuts are in place. Microsoft
; documents SHCNE_ASSOCCHANGED as the call that "instruct[s] the Shell to
; invalidate the icon and thumbnail cache" (SHChangeNotify, Remarks).
; Measured on Windows (v0.16.81 -> this build) was only the taskbar, which the
; window ICON_BIG below fixes; the effect of this call on Explorer and
; shortcut icons is taken from that documentation and was not measured.
;
; The call form is copied from tauri's own FileAssociation.nsh, which is
; included before this file and already defines these names, hence !ifndef.
; SHCNE_UPDATEITEM on the exe path is left out: it needs a wide-string
; argument that cannot be checked without a Windows build.
; It runs for fresh installs and for updater runs (/UPDATE) alike, and a
; failure cannot stop the install: System::Call has no error path here.
; The running app separately sets the window ICON_BIG (src/icon_refresh.rs),
; which is what the taskbar button shows.

!ifndef SHCNE_ASSOCCHANGED
  !define SHCNE_ASSOCCHANGED 0x08000000
!endif
!ifndef SHCNF_FLUSH
  !define SHCNF_FLUSH 0x1000
!endif

!macro NSIS_HOOK_POSTINSTALL
  ; uFlags is SHCNF_IDLIST (0, as the docs require for this event) | SHCNF_FLUSH.
  System::Call "shell32::SHChangeNotify(i,i,i,i) (${SHCNE_ASSOCCHANGED}, ${SHCNF_FLUSH}, 0, 0)"
!macroend

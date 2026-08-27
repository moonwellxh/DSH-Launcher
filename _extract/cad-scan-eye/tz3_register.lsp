;;; ======================================================================
;;; TZ3 plugin register/unregister tool (extracted from user acaddoc.lsp,
;;; 2026-08-17). PURE ASCII file: valid in both UTF-8 and GBK, satisfies
;;; the "AutoLISP files must be GBK" constraint.
;;;
;;; Purpose: persist-load/unload DLL or ARX via registry
;;;   HKCU\...\Applications (demand-load on AutoCAD startup)
;;; Commands:
;;;   REGDLL   - pick a DLL/ARX, register to registry; auto-load after
;;;              AutoCAD restart
;;;   UNREGDLL - enumerate registered plugins, select via dialog, confirm,
;;;              then unregister
;;; Notes:
;;;   - REGDLL writes registry via WScript.Shell, LOADCTRLS=2 (startup load)
;;;   - .NET DLL target framework must match AutoCAD runtime
;;;     (<=2024: .NET Framework 4.8 / >=2025: .NET 8)
;;;   - .arx is binary-bound to AutoCAD major version
;;; Load: APPLOAD this file then type REGDLL / UNREGDLL, or add to acaddoc.lsp
;;; ======================================================================
(defun c:REGDLL (/ wsh key dll app ext managed)
  (if (setq dll (getfiled "Pick DLL/ARX to persist-load" "" "dll;arx" 0))
    (progn
      (setq dll     (vl-string-translate "/" "\\" dll))    ; normalize backslash
      (setq app     (vl-filename-base dll))                ; filename as reg name
      (setq ext     (strcase (vl-filename-extension dll))) ; ".DLL" or ".ARX"
      (setq managed (if (= ext ".ARX") 0 1))               ; arx = unmanaged
      (setq key (strcat "HKCU\\" (vlax-product-key) "\\Applications\\" app))
      (setq wsh (vlax-create-object "WScript.Shell"))
      (vlax-invoke wsh 'RegWrite (strcat key "\\DESCRIPTION") app "REG_SZ")
      (vlax-invoke wsh 'RegWrite (strcat key "\\LOADER") dll "REG_SZ")
      (vlax-invoke wsh 'RegWrite (strcat key "\\LOADCTRLS") 2 "REG_DWORD")
      (vlax-invoke wsh 'RegWrite (strcat key "\\MANAGED") managed "REG_DWORD")
      (vlax-release-object wsh)
      (princ (strcat "\nRegistered " app
                     (if (= managed 1) " (.NET managed)" " (ObjectARX unmanaged)")
                     ", auto-loads after AutoCAD restart:\n" dll))
      ;; usage reminder shown by type
      (if (= managed 0)
        (princ (strcat "\n[Note] .arx is binary-bound to AutoCAD major version:"
                       " same series (e.g. R24.x) works; cross major version"
                       " (R24->R25) needs a recompiled file."
                       "\n       Current kernel R" (getvar "ACADVER")
                       "; if load fails after upgrade, run UNREGDLL first,"
                       " then register the rebuilt arx."))
        (princ (strcat "\n[Note] .NET DLL target framework must match AutoCAD"
                       " runtime: <=2024 is .NET Framework 4.8, >=2025 is"
                       " .NET 8; mismatch fails to load."))
      )
    )
    (princ "\nCancelled, no changes made.")
  )
  (princ)
)

(defun c:UNREGDLL (/ base apps items dclfile f dcl_id ret sel app path key wsh res cfm)
  ;; enumerate registered plugins in registry
  (setq base (strcat "HKEY_CURRENT_USER\\" (vlax-product-key) "\\Applications"))
  (setq apps (vl-registry-descendents base))
  (if (null apps)
    (alert "No persist-load plugin registered yet.")
    (progn
      ;; list items: reg name + loader path
      (setq items
        (mapcar
          '(lambda (a / p)
             (setq p (vl-registry-read (strcat base "\\" a) "LOADER"))
             (strcat a "  ----  " (if p p "(no path)")))
          apps))
      ;; write temp DCL file: list dialog + confirm dialog
      (setq dclfile (vl-filename-mktemp "unreg.dcl"))
      (setq f (open dclfile "w"))
      (write-line "unreg : dialog { label = \"Select plugin to unregister\";" f)
      (write-line "  : text { label = \"List from registry; double-click to confirm.\"; }" f)
      (write-line "  : list_box { key = \"apps\"; width = 78; height = 12; allow_accept = true; }" f)
      (write-line "  ok_cancel;" f)
      (write-line "}" f)
      (write-line "confirm : dialog { label = \"Confirm unregister\";" f)
      (write-line "  : text { key = \"msg1\"; width = 66; }" f)
      (write-line "  : text { key = \"msg2\"; width = 66; }" f)
      (write-line "  : text { label = \"After unregister it no longer auto-loads; use REGDLL to re-register anytime.\"; }" f)
      (write-line "  : row {" f)
      (write-line "    : button { key = \"accept\"; label = \"Confirm\"; is_default = true; fixed_width = true; width = 12; }" f)
      (write-line "    : button { key = \"cancel\"; label = \"Cancel\"; is_cancel = true; fixed_width = true; width = 12; }" f)
      (write-line "  }" f)
      (write-line "}" f)
      (close f)
      ;; load and show dialog
      (setq dcl_id (load_dialog dclfile))
      (if (or (< dcl_id 0) (not (new_dialog "unreg" dcl_id)))
        (alert "Dialog creation failed.")
        (progn
          (start_list "apps")
          (mapcar 'add_list items)
          (end_list)
          (setq sel "0")
          (set_tile "apps" sel)
          (action_tile "apps" "(setq sel $value)(if (= $reason 4) (done_dialog 1))")
          (action_tile "accept" "(done_dialog 1)")
          (action_tile "cancel" "(done_dialog 0)")
          (setq ret (start_dialog))
          (if (/= ret 1)
            (princ "\nCancelled, no registry changes.")
            (progn
              (setq app  (nth (atoi sel) apps))
              (setq path (vl-registry-read (strcat base "\\" app) "LOADER"))
              ;; second confirmation: show reg name and path
              (if (not (new_dialog "confirm" dcl_id))
                (alert "Confirm dialog creation failed, aborted.")
                (progn
                  (set_tile "msg1" (strcat "About to unregister: " app))
                  (set_tile "msg2" (strcat "Loader path: " (if path path "(none)")))
                  (action_tile "accept" "(done_dialog 1)")
                  (action_tile "cancel" "(done_dialog 0)")
                  (setq cfm (start_dialog))
                  (if (/= cfm 1)
                    (princ "\nCancelled, registry unchanged.")
                    (progn
                      (setq key (strcat "HKCU\\" (vlax-product-key)
                                        "\\Applications\\" app "\\"))
                      (setq wsh (vlax-create-object "WScript.Shell"))
                      (setq res (vl-catch-all-apply 'vlax-invoke (list wsh 'RegDelete key)))
                      (vlax-release-object wsh)
                      (if (vl-catch-all-error-p res)
                        (princ (strcat "\nRegistry key for " app " not found."))
                        (princ (strcat "\nUnregistered " app ", no longer auto-loads after restart."))
                      )
                    )
                  )
                )
              )
            )
          )
        )
      )
      (if (> dcl_id 0) (unload_dialog dcl_id))
      (if dclfile (vl-file-delete dclfile))
    )
  )
  (princ)

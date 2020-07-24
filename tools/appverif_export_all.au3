; check repository for LICENSE information
; repo    :  https://github.com/fuzzah/fuzzaide
; author  :  https://github.com/fuzzah

#pragma compile(Console, true)

#RequireAdmin

#include <GUIConstantsEx.au3>
#include <WindowsConstants.au3>
#include <AutoItConstants.au3>
#include <WinAPIConv.au3>
#include <GuiListView.au3>
#include <File.au3>

Func main()
   If $CmdLine[0] < 1 Then
	  ConsoleWrite("Usage: " & @ScriptName & " C:\output\dir\path\" & @CRLF)
	  return 0
   EndIf

   Local $path = $CmdLine[1]

   If StringRight($path,1) <> "\" Then
	  $path = $path & "\"
   EndIf

   If FileExists($path) = 0 Then
	  ConsoleWrite("Path " & $path & " doesn't exist" & @CRLF)
	  return 1
   EndIf

   If StringInStr(FileGetAttrib($path), "D") = 0 Then
	  ConsoleWrite("Path " & $path & " is not directory" & @CRLF)
	  return 1
   EndIf

   ConsoleWrite("Open Application Verifier - Logs window. Waiting.. " & @CRLF)
   Local $hWnd = WinWaitActive("Application Verifier - Logs")

   Local $hList = ControlGetHandle($hWnd, "", "Button12")
   If $hList = 0 Then
	  ConsoleWriteError("Wasn't able to find ListBox control" & @CRLF)
	  Return 1
   EndIf

   Local $hSaveAs = ControlGetHandle($hWnd, "", "Button4")
    If $hSaveAs = 0 Then
	  ConsoleWriteError("Wasn't able to find SaveAs button" & @CRLF)
	  Return 1
   EndIf

   Local $pos = ControlGetPos($hWnd, "", "Button12")
   Local $x = 150
   Local $y = 200

   Local $tPoint = DllStructCreate("int X;int Y")
   DllStructSetData($tPoint, "X", $x)
   DllStructSetData($tPoint, "Y", $y)
   _WinAPI_ClientToScreen($hList, $tPoint)
   $x = DllStructGetData($tPoint, "X")
   $y = DllStructGetData($tPoint, "Y")
   MouseClick("left", $x, $y, 1, 5)
   Sleep(100)

   ; actually get handle of ListBox which is SysListView32
   $listClassName = ControlGetFocus($hWnd)
   If $listClassName == "" Then
	  ConsoleWriteError("Wasn't able to find ListBox control" & @CRLF)
	  Return 2
   EndIf
   $hList = ControlGetHandle($hWnd, "", $listClassName)

   Local $itemCount = _GUICtrlListView_GetItemCount($hList)

   If $itemCount < 1 Then
	  ConsoleWrite("No items found. Nothing to do! Leaving.. " & @CRLF)
	  Return 0
   EndIf

   ConsoleWrite("Found " & $itemCount & " items. Starting to iterate.. " & @CRLF)
   Sleep(500)

   For $i = $itemCount - 1 To 0 Step -1
	  _GUICtrlListView_SetItemSelected($hList, -1, False, False)
	  _GUICtrlListView_SetItemSelected($hList, $i, True, True)
	  Sleep(50)
	  ControlClick($hWnd, "", "Button4")
	  Local $hDialog = WinWaitActive("Export Log")

	  Local $hNameEdit = ControlGetHandle($hDialog, "", "Edit1")
	  If $hNameEdit = 0 Then
		 ConsoleWriteError("Wasn't able to find file name edit control" & @CRLF)
		 Return 3
	  EndIf

	  Local $fpath = ControlGetText($hDialog, "", "Edit1")
	  $fpath = $path & $fpath
	  ConsoleWrite("Saving item " & $itemCount - $i - 1 & " to path " & $fpath & @CRLF)
	  ControlSetText($hDialog, "", "Edit1", $fpath)
	  Sleep(50)

	  Local $hSave = ControlGetHandle($hDialog, "", "Button2")
	  If $hSave = 0 Then
		 ConsoleWriteError("Wasn't able to find Save button" & @CRLF)
		 Return 3
	  EndIf

	  ControlClick($hDialog, "", "Button2")
   Next

   ConsoleWrite("Done!" & @CRLF)

   Return 0
EndFunc

main()
package main

import "syscall"

// ShellExecute passes the fragment directly to the OS, never through a shell command or log.
func openBrowser(url string) {
	shell := syscall.NewLazyDLL("shell32.dll").NewProc("ShellExecuteW")
	operation, _ := syscall.UTF16PtrFromString("open")
	target, _ := syscall.UTF16PtrFromString(url)
	shell.Call(0, uintptrPointer(operation), uintptrPointer(target), 0, 0, 1)
}

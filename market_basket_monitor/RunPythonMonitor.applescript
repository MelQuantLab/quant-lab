-- Helper AppleScript called by the AutoMonitor VBA macro via AppleScriptTask.
-- This file must live in: ~/Library/Application Scripts/com.microsoft.Excel/
-- (create that folder if it doesn't exist yet). See README.md section 4.

on runShellCommand(cmdString)
	do shell script cmdString
end runShellCommand

on createDraft(payload)
	set AppleScript's text item delimiters to "||"
	set payloadParts to text items of payload
	set recipientAddress to item 1 of payloadParts
	set subjectText to item 2 of payloadParts
	set attachmentPath to item 3 of payloadParts
	set AppleScript's text item delimiters to ""

	tell application "Mail"
		set draftMessage to make new outgoing message with properties {visible:true, subject:subjectText, content:"Attached is the latest MelQuantLab weekly research report." & return & return & "Historical research only — not investment advice." & return}
		tell draftMessage
			make new to recipient at end of to recipients with properties {address:recipientAddress}
			make new attachment with properties {file name:(POSIX file attachmentPath)} at after the last paragraph
		end tell
		activate
	end tell

	return "Draft created"
end createDraft

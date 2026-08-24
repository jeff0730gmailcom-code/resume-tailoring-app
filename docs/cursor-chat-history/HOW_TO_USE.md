# How to reuse this chat history on another Cursor account

Cursor does **not** copy chats when you switch login. History is local to this PC / this Cursor profile.

This folder is a **backup inside the project**, so the other account can still read it.

## After you log in with the new account

1. Open the same folder: `c:\Users\admin\Documents\New folder`
2. Start a **new** Agent chat
3. Attach context:
   - `@docs/PROJECT_HANDOFF.md` (read this first — short summary)
   - optionally `@docs/cursor-chat-history/agent-transcripts` if you need full past chats
4. Example first message:

   > Read `@docs/PROJECT_HANDOFF.md`. Continue work on this Resume Tailor app from that context.

## Optional: export from Cursor UI

In the old account, open a chat → **⋯** menu → **Export Chat** if it exists. Save the file under `docs/cursor-chat-history/`.

## Optional: chats in Cursor’s sidebar

Community extension **Cursor Chat Transfer** can export/import chats into the native chat list. After import, fully quit Cursor and reopen.

Same Windows user + same project path often still shows old chats even after switching Cursor login. If they disappear, use the files in this folder.

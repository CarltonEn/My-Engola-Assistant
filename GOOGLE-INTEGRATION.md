# Google / Gmail Integration Plan

Engola should use OAuth 2.0 rather than storing a Gmail password.

Planned capabilities after the owner explicitly authorizes Google access:
- Search/read Gmail messages
- Summarize and classify messages
- Draft replies
- Send mail when the owner has granted the required action permission
- Search Google Drive files
- Use Calendar for scheduling
- Use Contacts where authorized

Required production configuration:
- GOOGLE_CLIENT_ID
- GOOGLE_CLIENT_SECRET
- GOOGLE_REDIRECT_URI
- encrypted OAuth token storage in Supabase/Postgres or a managed secret store

Default permission policy:
- Read/search: allowed after connection
- Draft: allowed
- Send/delete/archive/forward: ask before consequential actions unless the owner explicitly establishes a standing permission
- Financial/legal/security-sensitive messages: always require confirmation

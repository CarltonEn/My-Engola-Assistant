# Engola integrations — token and authorization policy

Engola uses runtime secrets and OAuth state only. No token belongs in source, browser JavaScript, screenshots, tests, or chat logs.

## How we will work

When a real integration is next in priority, the owner provides authorization through the provider's official flow. Engola then stores only the minimum server-side credential/token data required by that integration and reports its actual state.

I will guide the owner step-by-step for each provider when we activate it. We do not request every token in advance.

## Provider families

### Telegram archive
Required when activating cold archive:
- Bot token from BotFather
- Private archive chat/channel ID

The token stays on the Engola server/Termux worker. The archive chat should be private.

### Google / Gmail / Calendar
Required when activating Google features:
- Google OAuth client configuration
- Owner OAuth consent
- Only the scopes needed for the feature

Gmail archive is a secondary archive for smaller files; Telegram/object storage remains the preferred durable-file direction.

### GitHub
Required when activating GitHub capabilities:
- GitHub OAuth application credentials
- Owner authorization
- Narrow scopes matching the requested operation

Repository writes, issue creation and other consequential actions remain approval-gated.

### Future providers
Drive, S3-compatible storage, OneDrive, Dropbox and other services should implement the provider contract rather than creating provider-specific storage logic throughout Engola.

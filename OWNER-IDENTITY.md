# Engola Owner Identity Architecture

Owner: Engola Innocent

## Authentication
Primary owner authentication uses WebAuthn/passkeys with required user verification. The biometric operation (fingerprint/face/device PIN) remains inside the device authenticator; Engola receives the cryptographic assertion, not the biometric template.

## Visual identity
Engola may maintain a private visual reference profile for owner-facing experiences, but photographs must never be treated as the sole authentication factor. Visual matching is a secondary signal and should be performed locally or in a private trusted service. Do not commit the owner's photographs or National ID images to a public repository.

Recommended policy:
1. Keep a small set of owner reference images in private object storage/device storage.
2. Use face matching only as an additional confidence signal.
3. Require WebAuthn/user verification for privileged actions.
4. Never store or process the National ID image unless a specific lawful workflow requires it.
5. Provide an owner-controlled delete/reset function for the visual profile.

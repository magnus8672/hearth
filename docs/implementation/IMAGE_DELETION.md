# Delete generated images

> Addresses, host labels and accounts shown here are illustrative placeholders. Use your own private deployment configuration.

Deployed to the existing head at `10.20.30.10` on 17 September 2026.

The private Images gallery offers **Delete image** beside **Save PNG** and **Use settings** on completed or stopped jobs. A confirmation names both the gallery and private chat effect. Successful deletion removes the card immediately and survives refresh or a new session. Errors leave the card available for retry. Pending and running jobs must finish or stop first.

`DELETE /api/v1/images/{job_id}` requires the user application session, exact origin, CSRF token and the image owner's PostgreSQL scope. Administrator privileges do not grant access to another user's private gallery. Shared-channel images are excluded from this endpoint; channel moderation remains separate work.

Migration `0021` adds a deletion timestamp and a conversation attachment `deleted` state. Deletion erases the saved PNG bytes from both `image_jobs` and `conversation_images`, clears byte receipts, removes the image from gallery results and frees its saved-image quota slot. Private chats display **Image deleted** without an image request or download link. Both artifact URLs return 404. Removing one batch item preserves its siblings; a completed item can be removed while later items render without being restored by the batch coordinator. A deleted attachment cannot become an automatic variation reference.

Small identity records and generation parameters remain for retry protection and existing variation references. Replaying a deleted gallery request returns 410 instead of starting another render. Conversation text remains history. This feature does not erase files previously downloaded by a person, provider-side outputs such as Fooocus files, existing database backups or historical exports. It is not a complete account-erasure or storage-retention implementation.

## Verification

- 25 focused tests passed against restricted PostgreSQL roles in a temporary database on the existing head, removed afterward. Three opt-in live generation tests were skipped; no GPU inference was needed for deletion.
- Checks include ownership, anonymous/admin rejection, CSRF and origin validation, both blob copies, fresh-session persistence, replay protection, quota release, batch siblings and in-flight batches, pending-job rejection, channel exclusion and reference integrity.
- One Playwright interaction test passed against the deployed HTTPS production bundle with synthetic API responses and a harmless PNG. It covers confirmation dismissal, failure/retry, removal, refresh, a persisted chat placeholder and mobile overflow. Certificate validation stayed enabled. It does not claim a real-user end-to-end deletion.
- Contract generation, Python lint, TypeScript checks and both production builds passed. The VM applied migration `0021` with a private backup; pre/post migration account counts and saved image byte totals matched. Existing user images were not deleted during qualification.

See [validation evidence](../../evidence/images/2026-09-17-deletion/validation.json). Refresh the workspace once to load the new action. No full release gate changes status.

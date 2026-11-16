# Drive to YouTube cloud publisher

Publishes one eligible video per execution, approximately every 15 minutes, using a standard GitHub-hosted Ubuntu runner. This public repository contains code only. OAuth credentials, account identity and Drive folder IDs are configured in Actions Secrets.

Shorts must be vertical and at most 180 seconds. Landscape videos require a matching image with the same filename stem. Published files are archived in Drive. Uncertain uploads are marked for review and never blindly uploaded again.

Manual runs default to a read-only connectivity check. Scheduled runs publish only when AUTO_PUBLISH_ENABLED is true. Empty queues produce no uploads.

Required Secrets: AUTO_PUBLISH_ENABLED, GOOGLE_OAUTH_TOKEN_JSON, GOOGLE_OWNER_EMAIL, YOUTUBE_CHANNEL_ID, YOUTUBE_CHANNEL_HANDLE, DRIVE_SHORTS_FOLDER_ID, DRIVE_HORIZONTAL_FOLDER_ID, DRIVE_POSTED_SHORTS_ID, DRIVE_POSTED_HORIZONTAL_ID, DRIVE_REVIEW_SHORTS_ID, DRIVE_REVIEW_HORIZONTAL_ID.

Standard hosted runners in public repositories have free Actions compute. Account-wide billing restrictions may still prevent execution. No paid runner or storage service is configured. OAuth grants may be revoked and YouTube API quotas still apply.

Run tests: `python -m unittest -q`.

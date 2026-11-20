# Drive to YouTube cloud publisher

Checks the queue every four hours using a GitHub-hosted Ubuntu runner. Publishes at most **two videos per calendar day** in the America/Los_Angeles time zone (San Diego), with **at least four hours** between videos and at most one upload per run. Posting window: 09:00–19:00 San Diego time. After the two daily slots have been used, subsequent scheduled runs **do not scan the pending videos** until the next San Diego calendar day. Counts are persisted in Drive using posted/review folders and appProperties (not in ephemeral GitHub Actions storage). This public repository contains code only. OAuth credentials, account identity and Drive folder IDs are configured in Actions Secrets.

Shorts must be vertical and at most 180 seconds. Landscape videos require a matching image with the same filename stem. Published files are archived in Drive. Uncertain uploads are marked for review and never blindly uploaded again.

Runs publish only when AUTO_PUBLISH_ENABLED is true. Empty queues produce no uploads. For a read-only connectivity check, manually run with check_only=true. The default remains publishing to preserve existing external schedule dispatches.

Required Secrets: AUTO_PUBLISH_ENABLED, GOOGLE_OAUTH_TOKEN_JSON, GOOGLE_OWNER_EMAIL, YOUTUBE_CHANNEL_ID, YOUTUBE_CHANNEL_HANDLE, DRIVE_SHORTS_FOLDER_ID, DRIVE_HORIZONTAL_FOLDER_ID, DRIVE_POSTED_SHORTS_ID, DRIVE_POSTED_HORIZONTAL_ID, DRIVE_REVIEW_SHORTS_ID, DRIVE_REVIEW_HORIZONTAL_ID.

Standard hosted runners in public repositories have free Actions compute. Account-wide billing restrictions may still prevent execution. No paid runner or storage service is configured. OAuth grants may be revoked and YouTube API quotas still apply.

Run tests: `python -m unittest -q`.

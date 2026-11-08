# Privacy Policy: Ashwal XAU Publisher

_Last updated: 8 November 2026_

Ashwal XAU Publisher ("the app") is a private, single-user tool run by S Syed Ashwal (@ashwal.xau). It uploads Ashwal's own short videos to his own YouTube channel and Instagram account on a schedule, from GitHub Actions.

## YouTube API Services
- The app uses **YouTube API Services** to upload videos (`videos.insert`) and to confirm the connected channel (`channels.list`).
- By using the app you agree to be bound by the **YouTube Terms of Service**: https://www.youtube.com/t/terms
- The **Google Privacy Policy** applies to data handled through YouTube API Services: http://www.google.com/policies/privacy

## What data the app accesses
- An OAuth access/refresh token for the channel owner's Google account, with the `youtube.upload` and `youtube.readonly` scopes.
- The channel's ID and title (read once to confirm the right channel).
- The app does **not** collect, store, display, sell or share any YouTube data or any data about other users. It has only one user: the channel owner.

## How data is stored
- The refresh token is stored only as an encrypted GitHub Actions secret in this repository and is used only by its own workflows.
- Upload results (video ID and link) are written to `schedule.json` in this repository so the same video is never uploaded twice.

## Deletion and revoking access
- You can revoke the app's access at any time at the Google security settings page: https://security.google.com/settings/security/permissions
- On revocation or on request, the stored token is deleted from the repository secrets within 7 days, and no other YouTube data is kept.
- To request deletion, email syedashwal2004@gmail.com.

## Contact
S Syed Ashwal · syedashwal2004@gmail.com

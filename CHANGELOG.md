# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### ⚠️ Deployment Notes

This release contains **database migrations** that must be applied before starting the new version:

```bash
alembic upgrade head
```

If you want to use email-based user invitations or password resets, configure the Mailjet integration either via environment variables or through the new admin Settings page (see below).

### New Features

#### Admin Messages
- Admins can now create site-wide messages displayed to all users on the front page (closes #9)
- Messages support multiple placement options, an optional icon, and multi-language translations

#### User Invitations via Email (closes #10)
- Admins can invite new users by email; the user receives a link to set their password
- Powered by the [Mailjet](https://www.mailjet.com/) API
- Configure by setting the following environment variables, or through the new admin Settings page:
  - `MAILJET_API_KEY`
  - `MAILJET_API_SECRET`
  - `MAILJET_SENDER`

#### Password Reset Email
- Users can request a password-reset link sent to their registered email address
- Requires Mailjet to be configured (see above)

#### Admin Settings Page (closes #11)
- New settings page in the admin panel for managing application-level configuration (e.g., Mailjet credentials, default language)

#### Enhanced Start Page (closes #8)
- Front page now shows an upcoming-events list and a calendar overview

#### ICS Calendar Feed Customization (closes #6)
- Users can choose which activities appear in their personal ICS calendar feed

### Improvements

- Markdown is now supported in schedule notes
- ICS public links are now visible and accessible to users (closes #7)
- Improved duplicate-schedule prevention
- Password length is now enforced when an admin creates a user (closes #12)

### Bug Fixes

- Fixed bulk edits of schedule entries
- Fixed offline editing behavior
- Fixed ICS link visibility

### Database Migrations

The following Alembic migrations are included and **must be applied** in order:

| Migration | Description |
|---|---|
| `20260209_add_rbac_models` | Adds role-based access control tables |
| `20260209_add_role_permission_resource` | Adds resource-scoped permissions |
| `20260209_add_org_fk_taxonomy` | Adds organisation foreign key to taxonomy |
| `20260213_add_language_columns` | Adds language/locale columns to users and settings |
| `20260226_add_activity_default_times` | Adds default start/end times to activities |
| `20260226_add_entry_start_end` | Adds explicit start/end columns to schedule entries |
| `20260226_add_user_calendar_token` | Adds per-user token for ICS calendar feeds |
| `20260302_schedule_unique_idx` | Adds unique index to prevent duplicate schedules |
| `20260305_add_user_personal_calendar_activities` | Stores per-user activity preferences for ICS feeds |
| `20260306_add_admin_message_icon` | Adds icon field to admin messages |
| `20260307_add_admin_message_translations` | Adds translation support to admin messages |
| `20260309_add_admin_message_placement` | Adds placement option to admin messages |
| `20260309_add_invitations_app_settings` | Adds invitation tokens and application settings tables |
| `20260311_add_user_email` | Adds email address column to users |

### Frontend Toolchain Upgrade

- Upgraded to `@quasar/app-vite` v2
- Upgraded to Vite 7
- Upgraded to Node.js 20
- Switched to the new Quasar i18n plugin
- Converted `quasar.config` to ESM format

### CI / Security

- Added GitHub Actions CI workflow for backend tests and frontend build checks
- Fixed missing `permissions` declarations in workflow files
- Fixed incomplete multi-character input sanitization

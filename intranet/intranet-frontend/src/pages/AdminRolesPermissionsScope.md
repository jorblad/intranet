Usage: Scoping permissions to resources

UI changes in `AdminRoles.vue` include two optional fields in the permissions dialog:
- `Scoped` checkbox: when checked, shows inputs for `resource_type` and `resource_id`.
- When saving, the frontend calls `PUT /api/rbac/roles/{role_id}/permissions?resource_type=...&resource_id=...`

Backend changes add a `role_permission_resources` table and endpoints now accept `resource_type` and `resource_id` query parameters.

This file is documentation only.

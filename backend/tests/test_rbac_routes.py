import pytest

from app.main import app


def test_apply_program_preset_route_exists():
    paths = [r.path for r in app.router.routes]
    assert "/api/rbac/roles/{role_id}/apply-program-preset" in paths

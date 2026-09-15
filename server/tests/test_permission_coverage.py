"""CI guard: every route must be permission-checked or explicitly public.

Without this, the RBAC matrix silently stops covering new endpoints the
moment someone adds a route and forgets the dependency (plan section 6.3).
Runs with no database -- it only inspects the app's route table.
"""
from app.main import app
from app.permissions import PUBLIC_ROUTES, RequirePermission


def _iter_routes(routes):
    """Flatten FastAPI's route tree.

    Routes added via app.include_router() are not flattened into app.routes
    directly on current FastAPI/Starlette -- each shows up as an
    `_IncludedRouter` wrapper holding the real APIRouter (with routes
    already carrying their final, prefixed paths) on `.original_router`.
    Recurse through those so this test still sees every real route.
    """
    for route in routes:
        if hasattr(route, "path") and hasattr(route, "methods"):
            yield route
        elif hasattr(route, "original_router"):
            yield from _iter_routes(route.original_router.routes)


def test_every_route_is_protected_or_explicitly_public():
    uncovered = []
    for route in _iter_routes(app.routes):
        methods = getattr(route, "methods", None)
        path = getattr(route, "path", None)
        if methods is None or path is None:
            continue
        for method in methods:
            if method == "HEAD":
                continue
            key = (method, path)
            if key in PUBLIC_ROUTES:
                continue
            dependant = getattr(route, "dependant", None)
            has_permission_dep = dependant is not None and any(
                isinstance(getattr(sub, "call", None), RequirePermission)
                for sub in dependant.dependencies
            )
            if not has_permission_dep:
                uncovered.append(key)

    assert uncovered == [], (
        f"Routes missing a permission check or a PUBLIC_ROUTES entry: {uncovered}"
    )

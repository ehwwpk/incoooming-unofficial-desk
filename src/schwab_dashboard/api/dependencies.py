from fastapi import Request

from schwab_dashboard.container import Container


def get_container(request: Request) -> Container:
    container: Container = request.app.state.container
    return container

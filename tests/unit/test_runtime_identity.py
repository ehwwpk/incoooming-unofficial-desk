from schwab_dashboard.infrastructure.runtime.identity import (
    APP_ID,
    current_build_id,
    new_runtime_identity,
)


def test_runtime_identity_is_stable_for_the_loaded_build() -> None:
    first = current_build_id()
    second = current_build_id()

    assert first == second
    assert len(first) == 16
    assert all(character in "0123456789abcdef" for character in first)


def test_runtime_identity_exposes_no_local_secret_or_account_data() -> None:
    identity = new_runtime_identity().as_dict()

    assert identity["app"] == APP_ID
    assert isinstance(identity["pid"], int)
    assert set(identity) == {"app", "version", "pid", "started_at", "build_id"}

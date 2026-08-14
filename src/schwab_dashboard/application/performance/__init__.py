"""Deposit-neutral portfolio performance projections.

The package initializer intentionally has no eager imports. Dashboard models
refer to the performance data contract, while the performance calculator also
accepts dashboard position models; importing the orchestration layer here would
create a circular dependency during application startup.
"""

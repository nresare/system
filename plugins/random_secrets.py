# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: The manifest-builder contributors
"""Shared random-secret configuration and manifest generation for plugins."""

from collections.abc import Sequence
from pathlib import Path


def parse_random_secrets(data: dict, source_file: Path) -> list[str] | None:
    """Normalize the 'random-secret'/'random-secrets' fields into a list of names.

    'random-secret' names a single secret key; 'random-secrets' names a list.
    Specifying both is an error.
    """
    random_secret = data.get("random-secret")
    random_secrets = data.get("random-secrets")

    if random_secret is not None and random_secrets is not None:
        raise ValueError(
            f"Cannot specify both 'random-secret' and 'random-secrets' in {source_file}"
        )

    if random_secret is not None:
        if not isinstance(random_secret, str):
            raise ValueError(f"'random-secret' must be a string in {source_file}")
        return [random_secret]

    if random_secrets is not None:
        if not isinstance(random_secrets, list) or not all(
            isinstance(secret, str) for secret in random_secrets
        ):
            raise ValueError(
                f"'random-secrets' must be a list of strings in {source_file}"
            )
        return random_secrets

    return None


RANDOM_SECRETS_MOUNT_PATH = "/random-secrets"


def inject_random_secrets(
    docs: list[dict],
    random_secrets: Sequence[str],
    namespace: str,
    k8s_name: str,
) -> None:
    """Emit a RandomSecret and mount its generated Secret at /random-secrets.

    The randomsecret controller (https://github.com/portswigger/randomsecret)
    reconciles a RandomSecret into a Secret of the same name in the same
    namespace, populating one entry per name in ``spec.secrets``.
    """
    if not random_secrets:
        return

    docs.append(
        {
            "apiVersion": "noa.re/v1alpha1",
            "kind": "RandomSecret",
            "metadata": {"name": k8s_name, "namespace": namespace},
            "spec": {"secrets": [{"name": secret} for secret in random_secrets]},
        }
    )

    for doc in docs:
        if doc.get("kind") != "Deployment":
            continue

        pod_spec = (
            doc.setdefault("spec", {}).setdefault("template", {}).setdefault("spec", {})
        )
        for container in pod_spec.get("containers", []):
            container.setdefault("volumeMounts", []).append(
                {"name": "random-secrets", "mountPath": RANDOM_SECRETS_MOUNT_PATH}
            )
        pod_spec.setdefault("volumes", []).append(
            {"name": "random-secrets", "secret": {"secretName": k8s_name}}
        )

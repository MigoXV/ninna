"""HF upload worker: endpoint globals are isolated to this short-lived process."""

from __future__ import annotations

import json
import sys


def main():
    from huggingface_hub import HfApi
    from huggingface_hub.utils import RepositoryNotFoundError

    value = json.load(sys.stdin)
    api = HfApi(endpoint=value["endpoint"], token=value["token"] or False)
    try:
        try:
            api.repo_info(value["repo_id"], repo_type=value["kind"])
        except RepositoryNotFoundError:
            api.create_repo(value["repo_id"], repo_type=value["kind"], private=value["private"])
        commit = api.upload_folder(
            repo_id=value["repo_id"],
            repo_type=value["kind"],
            folder_path=value["folder"],
            commit_message=value["message"],
        )
        print(json.dumps({"revision": commit.oid}))
    except Exception as exc:
        response = getattr(exc, "response", None)
        print(
            json.dumps(
                {"error": type(exc).__name__, "status_code": getattr(response, "status_code", None)}
            )
        )
        raise SystemExit(1)


if __name__ == "__main__":
    main()

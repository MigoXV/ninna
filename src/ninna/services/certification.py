from __future__ import annotations

import copy
import threading
import uuid

from ninna.domain.schemas import CreateRun
from ninna.services.platform import write_json
from ninna.storage.repository import now


def default_request(recipe="mnist-adam", version="v1", snapshot="current"):
    return {
        "training_spec": {
            "dataset": {"name": "mnist", "version": "v2"},
            "model": {"name": "mnist-cnn", "version": "v2"},
            "recipe": {"name": recipe, "version": version},
        },
        "execution_spec": {
            "runtime": {"name": "mnist-pytorch-runtime", "version": "v2"},
            "workspace": {"name": "mnist-hf", "snapshot": snapshot},
            "resources": {"device": "cpu", "gpu_count": 0, "cpu_threads": 4, "memory_mb": 4096},
        },
    }


class Certification:
    def __init__(self, platform):
        self.platform = platform
        self.lock = threading.Lock()

    def start(self, quick=False):
        with self.lock:
            for previous in self.platform.repo.list("certifications"):
                if previous["status"] == "RUNNING":
                    return previous
            record = {
                "id": "cert-" + uuid.uuid4().hex[:12],
                "created_at": now(),
                "finished_at": None,
                "status": "RUNNING",
                "profile": "quick" if quick else "full",
                "threshold": 0.95 if quick else 0.98,
                "checks": [],
                "run_ids": [],
                "failure_reason": None,
            }
            self.platform.repo.save("certifications", record)
            threading.Thread(
                target=self.execute, args=(record,), daemon=True, name="ninna-certification"
            ).start()
            return record

    def execute(self, record):
        platform = self.platform

        def save():
            platform.repo.save("certifications", record)
            directory = platform.settings.state / "certifications"
            directory.mkdir(exist_ok=True)
            write_json(directory / (record["id"] + ".json"), record)

        def check(name, ok, evidence=None):
            record["checks"].append(
                {"name": name, "status": "PASS" if ok else "FAIL", "evidence": evidence}
            )
            save()
            if not ok:
                raise ValueError(name + " failed")

        try:
            initialization = platform.initialize()
            conversion = initialization["conversion"]
            check("HF dataset conversion", conversion["all_images_and_labels_equal"], conversion)
            check(
                "HF model and preprocessing alignment",
                conversion["preprocessing_exact"] and conversion["logits_exact"],
            )
            check(
                "Runtime available",
                True,
                platform.repo.asset("runtime", {"name": "mnist-pytorch-runtime", "version": "v2"})[
                    "image_id"
                ],
            )
            for kind in ["dataset", "model", "recipe", "workspace"]:
                check(kind.capitalize() + " registered", bool(platform.repo.assets(kind)))
            snap = platform.workspace_snapshot("mnist-hf")
            check("Workspace prepared", True, snap["snapshot"])
            runs = []
            for recipe in ["mnist-adam", "mnist-sgd"]:
                version = "quick-v1" if record["profile"] == "quick" else "v1"
                run = platform.create_run(
                    CreateRun.model_validate(default_request(recipe, version, snap["snapshot"]))
                )
                record["run_ids"].append(run["id"])
                save()
                check(recipe + ": Training Run created", True, run["id"])
                run = platform.wait(run["id"])
                runs.append(run)
                context = platform.get_run_diagnostic_context(run["id"])
                check(
                    recipe + ": Docker container created",
                    bool(run["container_id"]),
                    run["container_id"],
                )
                inspect = context["container"] or {}
                mounts = {m["Destination"]: m for m in inspect.get("Mounts", [])}
                for label, destination, source in [
                    ("Dataset mounted", "/dataset", run["assets"]["dataset"]["path"]),
                    (
                        "Workspace mounted",
                        "/workspace",
                        run["assets"]["workspace"]["snapshot_path"],
                    ),
                ]:
                    from pathlib import Path

                    mount = mounts.get(destination, {})
                    check(
                        recipe + ": " + label,
                        mount.get("Source") == platform.settings.host_path(Path(source))
                        and mount.get("RW") is False,
                        mount,
                    )
                process = context["process"] or {}
                observation = context["process-observation"] or {}
                check(
                    recipe + ": Training in container",
                    process.get("docker_env") is True
                    and process.get("run_id") == run["id"]
                    and process.get("hostname") == run["id"]
                    and inspect.get("Config", {}).get("Labels", {}).get("ninna.run_id") == run["id"]
                    and bool(observation.get("Processes")),
                    {"process": process.get("pid"), "observed": observation},
                )
                check(
                    recipe + ": Logs collected",
                    bool(context["stdout"])
                    and (platform.output(run["id"]) / "stderr.log").exists(),
                )
                check(recipe + ": Run SUCCESS", run["status"] == "SUCCESS", run["failure_reason"])
                metrics = run["metrics"]
                check(recipe + ": Metrics collected", bool(metrics))
                check(
                    recipe + ": Checkpoint saved",
                    (platform.output(run["id"]) / "checkpoint.pt").stat().st_size > 0,
                )
                verification = platform.verify_checkpoint(run)
                check(
                    recipe + ": Checkpoint reload", verification["checkpoint_reload"], verification
                )
                check(
                    recipe + ": HF model reload and inference",
                    verification.get("hf_reload")
                    and verification.get("hf_auto_model_reload")
                    and verification.get("hf_logits_exact"),
                    verification,
                )
                check(
                    recipe + ": Model updated",
                    metrics["initial_model_hash"] != metrics["trained_model_hash"]
                    and verification["trained_model_hash"] == metrics["trained_model_hash"],
                )
                check(
                    recipe + ": Loss decreased",
                    metrics["final_loss"] < metrics["initial_loss"],
                    {"initial": metrics["initial_loss"], "final": metrics["final_loss"]},
                )
                check(
                    recipe + ": Test accuracy",
                    verification["test_accuracy"] > record["threshold"]
                    and abs(verification["test_accuracy"] - metrics["test_accuracy"]) < 1e-9,
                    {"accuracy": verification["test_accuracy"], "threshold": record["threshold"]},
                )
            left, right = [copy.deepcopy(r["training_spec"]) for r in runs]
            left.pop("recipe")
            right.pop("recipe")
            check(
                "Recipe decoupling",
                left == right
                and runs[0]["execution_spec"] == runs[1]["execution_spec"]
                and runs[0]["training_spec"]["recipe"] != runs[1]["training_spec"]["recipe"],
                {"changed": ["training_spec.recipe"]},
            )
            record["status"] = "PASS"
        except Exception as exc:
            record["status"] = "FAIL"
            record["failure_reason"] = str(exc)
            if not record["checks"] or record["checks"][-1]["status"] != "FAIL":
                record["checks"].append(
                    {"name": "Certification execution", "status": "FAIL", "evidence": str(exc)}
                )
        finally:
            record["finished_at"] = now()
            save()

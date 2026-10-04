"""Materialize a declared datasets.load_dataset source as portable Parquet splits."""

from pathlib import Path
import json
import sys

import yaml
from datasets import load_dataset


def main():
    config = yaml.safe_load(Path(sys.argv[1]).read_text())
    source = config["source"]
    # Explicit loader arguments are preserved in invocation.yaml and result provenance.
    data = load_dataset(**source)
    output = Path(config["output_dir"])
    output.mkdir(parents=True, exist_ok=True)
    counts = {}
    for name, selection in config["splits"].items():
        if not name.isidentifier():
            raise ValueError("Split name must be an identifier")
        split = data[selection["source"]]
        start = selection.get("start", 0)
        stop = min(selection.get("stop", len(split)), len(split))
        if not 0 <= start < stop:
            raise ValueError(f"Empty or invalid split selection: {name}")
        split = split.select(range(start, stop))
        required = set(config.get("required_columns", []))
        if not required <= set(split.column_names):
            raise ValueError(f"Missing columns: {sorted(required - set(split.column_names))}")
        split.to_parquet(str(output / f"{name}.parquet"))
        counts[f"{name}_samples"] = len(split)
    (output.parent / "metrics.json").write_text(json.dumps(counts))


if __name__ == "__main__":
    main()

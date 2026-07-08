"""ManifestWriter - records SHA256, git info, and command for reproducibility."""

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


class ManifestWriter:
    """Write manifest JSON recording inputs/outputs SHA256 and git state."""

    def compute_sha256(self, filepath: str) -> str:
        h = hashlib.sha256()
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()

    def get_git_info(self) -> dict:
        tag = subprocess.run(
            ["git", "describe", "--tags", "--always"],
            capture_output=True,
            text=True,
        ).stdout.strip()  # --always: フォールバックとしてコミットハッシュを返す
        commit = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
        ).stdout.strip()
        return {"git_tag": tag or "(no-tag)", "git_commit": commit or "(unknown)"}

    def write(
        self,
        command: str,
        input_files: list,
        output_files: list,
        output_dir: str,
    ) -> str:
        """Write manifest JSON and return its path.

        Args:
            command: The CLI command string that produced the outputs.
            input_files: List of input file paths to hash.
            output_files: List of output file paths to hash.
            output_dir: Directory in which to write manifest_*.json.

        Returns:
            Path to the written manifest file.
        """
        timestamp = datetime.now(timezone.utc).isoformat()

        inputs_hashes = {}
        for f in input_files:
            p = Path(f)
            if p.exists():
                inputs_hashes[p.name + "_sha256"] = self.compute_sha256(f)

        outputs_hashes = {}
        for f in output_files:
            p = Path(f)
            if p.exists():
                outputs_hashes[p.name + "_sha256"] = self.compute_sha256(f)

        manifest = {
            "timestamp": timestamp,
            "command": command,
            "inputs": inputs_hashes,
            "outputs": outputs_hashes,
            **self.get_git_info(),
        }

        safe_ts = timestamp.replace(":", "-").replace("+", "").replace(".", "-")
        outpath = Path(output_dir) / f"manifest_{safe_ts}.json"
        outpath.parent.mkdir(parents=True, exist_ok=True)
        outpath.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
        return str(outpath)

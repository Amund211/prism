"""Run the rk4_all training chain: the 8 steps of the shipped sidecar
(prism reader/rk4_all.json, train.chain), in order, from this dir.

Usage: chain.py [--dry-run] [--steps 1-8 | --short] [--n N]
--steps: `3`, `1-4` or `1,2,7`. --short: step 8 only (needs kf4.pt,
v3k_s1.pkl, realk_all.pkl in $TABCAP_RESULTS/c2/).
--n: N of the c2_gen steps (test runs); needs an own $TABCAP_RESULTS.
A step is skipped when its output exists; c2_train resumes from its .ckpt.
Step output goes to $TABCAP_RESULTS/c2/logs/NAME.log (it has real names).
At the end: c2/chain.sha256, and rk4_all.onnx is compared with the sidecar.
"""

import argparse
import hashlib
import json
import os
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass, field
from importlib.resources import files
from pathlib import Path

import data
from paths import HERE, fixtures, results

PER_JOB = 2000  # c2_gen samples per job
COMP_MODES = ("comp", "compk")
NAMED_MODES = ("v3n", "v3k", *COMP_MODES)


@dataclass
class Step:
    num: int
    argv: list[str]
    name: str
    out: str  # file in c2/
    needs: list[str] = field(default_factory=list)  # files in c2/

    @property
    def script(self) -> str:
        return self.argv[0]


def sidecar() -> dict:
    p = files("prism.overlay.tabcap.reader").joinpath("rk4_all.json")
    return json.loads(p.read_text())


def steps(n: int | None = None) -> list[Step]:
    out = []
    for s in sidecar()["train"]["chain"]:
        argv = shlex.split(s["cmd"])
        if argv[0] == "c2_gen.py":
            if n is not None:
                argv[2] = str(n)
            out.append(Step(s["step"], argv, argv[1], f"{argv[1]}.pkl"))
        elif argv[0] == "c2_train.py":
            out.append(Step(s["step"], argv, argv[1], f"{argv[1]}.onnx", _needs(argv)))
        elif argv[0] == "c2_real.py":
            out.append(Step(s["step"], argv, "realk_all", "realk_all.pkl"))
        else:
            raise ValueError(f"unknown chain step: {s['cmd']}")
    return out


def _needs(argv: list[str]) -> list[str]:
    needs = [f"{d}.pkl" for d in argv[2].split(",")]
    for flag, fmt in (("--init", "{}.pt"), ("--extra", "{}.pkl")):
        if flag in argv:
            needs.append(fmt.format(argv[argv.index(flag) + 1].split(":")[0]))
    return needs


def made_files(s: Step) -> list[str]:
    return [s.out, f"{s.name}.pt"] if s.script == "c2_train.py" else [s.out]


def parse_steps(v: str) -> list[int]:
    nums: set[int] = set()
    for part in v.split(","):
        a, _, b = part.partition("-")
        nums.update(range(int(a), int(b or a) + 1))
    if not nums <= set(range(1, 9)):
        raise argparse.ArgumentTypeError(f"steps must be in 1-8: {v}")
    return sorted(nums)


def _dir(var: str) -> Path | None:
    v = os.environ.get(var)
    return Path(v) if v else None


def preflight(chosen: list[Step], n: int | None) -> tuple[list[str], list[str]]:
    """Missing inputs of the chosen steps (errors), and notes."""
    errors, notes = [], []
    c2 = results() / "c2"
    if n is not None:
        if n < PER_JOB or n % PER_JOB:
            errors.append(f"--n must be a multiple of {PER_JOB}")
        if (
            not os.environ.get("TABCAP_RESULTS")
            or results().resolve() == (HERE / "results").resolve()
        ):
            errors.append("--n needs TABCAP_RESULTS set to an own (not default) dir")
    made: set[str] = set()
    for s in chosen:
        if (c2 / s.out).exists():
            notes.append(f"step {s.num}: {s.out} exists, skip")
            made.update(made_files(s))
            continue
        for f in s.needs:
            if f not in made and not (c2 / f).exists():
                errors.append(f"step {s.num}: missing c2/{f}")
        if s.script == "c2_gen.py":
            packs = _dir("TABCAP_RESOURCE_PACKS")
            if not packs or not (packs / "fonts").is_dir():
                errors.append(f"step {s.num}: TABCAP_RESOURCE_PACKS/fonts not found")
            names = _dir("TABCAP_NAMES")
            if s.argv[7] in NAMED_MODES and not (names and names.is_file()):
                errors.append(f"step {s.num}: TABCAP_NAMES file not found")
            calib = fixtures() / "tabcap_synth_calib_2026-11-21"
            if s.argv[7] in COMP_MODES and not calib.is_dir():
                notes.append(f"step {s.num}: no {calib}, calib.py downloads it")
        if s.script == "c2_real.py":
            fx = fixtures() / data.manifest()["version"]
            if not fx.is_dir():
                errors.append(f"step {s.num}: fixtures not found: {fx}")
            if not (results() / "tl/cache_c2_v3_tf.pkl").is_file():
                errors.append(f"step {s.num}: missing tl/cache_c2_v3_tf.pkl")
        made.update(made_files(s))
    return errors, notes


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        while b := f.read(1 << 20):
            h.update(b)
    return h.hexdigest()


def write_shas(all_steps: list[Step]) -> None:
    c2 = results() / "c2"
    lines = [
        f"{sha256(c2 / f)}  {f}"
        for s in all_steps
        for f in made_files(s)
        if (c2 / f).exists()
    ]
    (c2 / "chain.sha256").write_text("".join(x + "\n" for x in lines))
    print(f"wrote {c2 / 'chain.sha256'}")
    onnx = c2 / "rk4_all.onnx"
    if onnx.exists():
        want = sidecar()["sha256"]
        got = sha256(onnx)
        print(f"rk4_all.onnx {'matches' if got == want else 'DIFFERS from'} sidecar")
        print(f"  got  {got}\n  want {want}")


def run(s: Step) -> None:
    c2 = results() / "c2"
    if (c2 / s.out).exists():
        print(f"step {s.num}: {s.out} exists, skip")
        return
    logs = c2 / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    log = logs / f"{s.name}.log"
    print(f"step {s.num}: python {shlex.join(s.argv)}  (log {log})", flush=True)
    t = time.monotonic()
    with log.open("a") as f:
        rc = subprocess.run(
            [sys.executable, *s.argv], cwd=HERE, stdout=f, stderr=subprocess.STDOUT
        ).returncode
    mins = (time.monotonic() - t) / 60
    if rc:
        raise SystemExit(f"step {s.num} failed (exit {rc}, {mins:.1f} min): see {log}")
    print(f"step {s.num}: done in {mins:.1f} min", flush=True)


def main() -> None:
    a = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    a.add_argument("--dry-run", action="store_true", help="print, do not run")
    g = a.add_mutually_exclusive_group()
    g.add_argument("--steps", type=parse_steps, default=list(range(1, 9)))
    g.add_argument("--short", action="store_true", help="step 8 only")
    a.add_argument("--n", type=int, help="N of the c2_gen steps (test runs)")
    o = a.parse_args()
    nums = [8] if o.short else o.steps
    all_steps = steps(o.n)
    chosen = [s for s in all_steps if s.num in nums]
    errors, notes = preflight(chosen, o.n)
    print(f"results: {results()}\nfixtures: {fixtures()}")
    for s in chosen:
        print(f"step {s.num}: python {shlex.join(s.argv)}")
    for x in notes:
        print(f"note: {x}")
    for x in errors:
        print(f"missing: {x}")
    if o.dry_run:
        return
    if errors:
        raise SystemExit("pre-flight check failed")
    for s in chosen:
        run(s)
    write_shas(all_steps)


if __name__ == "__main__":
    main()

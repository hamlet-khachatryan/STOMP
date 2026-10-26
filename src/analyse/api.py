from __future__ import annotations

import json
import math
import re
import time
import eliot
from dataclasses import replace
from functools import partial
from multiprocessing import Pool
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import gemmi

from common.logging import setup_eliot_logging
from analyse.muse.config import AggregationConfig
from analyse.muse.pipeline import (
    export_atom_csv,
    export_residue_csv,
    export_summary,
    run_muse,
    write_scored_pdb,
)
from analyse.muse.config import snr_map_config
from analyse.screen_report import generate_screen_report
from quantify.statistical_model import compute_significance_threshold
from quantify.utils import find_experiments, get_experiment_paths


_DEFAULT_K_FACTOR = 1.0
_DEFAULT_MAP_CAP = None  # highest cap quantified at this k

# stomp-quantify writes quantify_results/k_{k}_cap_{cap}/ and metadata/{stem}_null_params_k{k}_cap{cap}.json
_RUN_DIR_RE = re.compile(r"^k_(?P<k>.+)_cap_(?P<cap>\d+)$")
_NULL_PARAMS_RE = re.compile(r"^_null_params_k(?P<k>.+)_cap(?P<cap>\d+)\.json$")


def _parse_k_cap(text: str, pattern: re.Pattern) -> Optional[Tuple[float, int]]:
    """
    Parse (k, cap) from a quantify run name. Returns None if the name does not match
    """

    match = pattern.match(text)
    if not match:
        return None
    try:
        return float(match["k"]), int(match["cap"])
    except ValueError:
        return None


def _same_k(a: float, b: float) -> bool:
    """
    Compare k factors numerically so that k_1 and k_1.0 refer to the same run
    """

    return math.isclose(float(a), float(b), rel_tol=0.0, abs_tol=1e-9)


def _format_runs(runs: List[Tuple[float, int]]) -> str:
    if not runs:
        return "none"
    return "; ".join(f"k={k}, cap={cap}" for k, cap in sorted(runs))


def _resolve_map_path(paths: dict, k_factor: float, map_cap: Optional[int]) -> Tuple[Path, int]:
    """
    Locate the SNR CCP4 map for the given k_factor/map_cap and return it with its cap.
    Auto-detects the highest cap for this k_factor if map_cap is None
    """

    stem = paths["stem"]
    qdir = paths["quantify_dir"]

    if not qdir.exists():
        raise FileNotFoundError(
            f"No quantify_results directory found at {qdir}. "
            "Run 'stomp-quantify' before 'stomp-analyse'."
        )

    available: List[Tuple[float, int]] = []
    matching: Dict[int, Path] = {}
    for run_dir in sorted(p for p in qdir.iterdir() if p.is_dir()):
        parsed = _parse_k_cap(run_dir.name, _RUN_DIR_RE)
        snr_path = run_dir / f"{stem}_snr.ccp4"
        if parsed is None or not snr_path.exists():
            continue
        available.append(parsed)
        run_k, run_cap = parsed
        if not _same_k(run_k, k_factor):
            continue
        # prefer the folder named exactly as stomp-quantify names it for this k
        if run_cap not in matching or run_dir.name == f"k_{k_factor}_cap_{run_cap}":
            matching[run_cap] = snr_path

    if map_cap is not None:
        if map_cap in matching:
            return matching[map_cap], map_cap
        raise FileNotFoundError(
            f"SNR map not found for k={k_factor}, cap={map_cap} in {qdir}. "
            f"Available runs: {_format_runs(available)}. "
            "Pass --k_factor/--map_cap matching one of them, or --map_cap 0 to auto-detect the cap."
        )

    if matching:
        best_cap = max(matching)
        return matching[best_cap], best_cap

    raise FileNotFoundError(
        f"No SNR map found in {qdir} for k_factor={k_factor}. "
        f"Available runs: {_format_runs(available)}. "
        "Run 'stomp-quantify' with this k, or provide a map explicitly with --map_path."
    )


def _run_from_map_location(
    map_path: Path, k_factor: float, map_cap: Optional[int]
) -> Tuple[float, Optional[int]]:
    """
    Return the (k, cap) of the quantify run an explicit map belongs to.

    A map inside quantify_results/k_{k}_cap_{cap}/ was made by that run, so its
    null parameters are used even if --k_factor/--map_cap say otherwise.
    Maps from anywhere else fall back to the flags.
    """

    parsed = _parse_k_cap(Path(map_path).parent.name, _RUN_DIR_RE)
    if parsed is None:
        return k_factor, map_cap

    run_k, run_cap = parsed
    if not _same_k(run_k, k_factor) or (map_cap is not None and map_cap != run_cap):
        print(
            f"Warning: --map_path is in a k={run_k}, cap={run_cap} run, "
            f"not k={k_factor}, cap={map_cap}. Using k={run_k}, cap={run_cap} for null params."
        )
    return run_k, run_cap


def _resolve_model_path(paths: dict) -> Path:
    """Return the original model path"""
    model_path = paths["original_pdb"]
    if not model_path.exists():
        raise FileNotFoundError(
            f"Original model not found at {model_path}. "
            "Run 'stomp-debias' first to generate the processed structure."
        )
    return model_path


def _load_null_params(paths: dict, k_factor: float, map_cap: Optional[int]) -> Optional[dict]:
    """
    Load the fitted null-distribution parameters for exactly this k_factor and map_cap.
    Parameters from other runs are never used, since they describe a different SNR map
    """

    stem = paths["stem"]
    metadata_dir = paths["metadata_dir"]
    candidates = sorted(metadata_dir.glob(f"{stem}_null_params_k*_cap*.json")) if metadata_dir.exists() else []

    available: List[Tuple[float, int]] = []
    match: Optional[Path] = None
    for path in candidates:
        parsed = _parse_k_cap(path.name[len(stem):], _NULL_PARAMS_RE)
        if parsed is None:
            continue
        available.append(parsed)
        if map_cap is not None and _same_k(parsed[0], k_factor) and parsed[1] == map_cap:
            if match is None or path.name == f"{stem}_null_params_k{k_factor}_cap{map_cap}.json":
                match = path

    if match is None:
        print(
            f"Warning: no null distribution parameters for k={k_factor}, cap={map_cap} in "
            f"{metadata_dir} (available: {_format_runs(available)}). "
            "Significance threshold will use MUSE paper defaults. "
            "Re-run 'stomp-quantify' with these settings to generate them."
        )
        return None

    with open(match) as fh:
        return json.load(fh)


def _infer_resolution(paths: dict) -> float:
    """
    Infer resolution in Ångströms from the first available MTZ file
    """

    stem = paths["stem"]
    results_dir = paths["results_dir"]

    canonical = results_dir / f"{stem}_0" / f"{stem}_0.mtz"
    if canonical.exists():
        return gemmi.read_mtz_file(str(canonical)).resolution_high()

    all_mtz = list(results_dir.glob("*/*.mtz"))
    if not all_mtz:
        raise FileNotFoundError(
            f"No MTZ files found in {results_dir}. "
            "Run 'stomp-debias' to generate omission map ensembles."
        )
    return gemmi.read_mtz_file(str(all_mtz[0])).resolution_high()

def _analyse_single(
    paths: dict,
    map_path: Optional[str],
    model_path: Optional[str],
    k_factor: float,
    map_cap: Optional[int],
    significance_alpha: float = 0.05,
) -> None:
    """
    Run MUSE analysis for one experiment and write results to analyse_results/
    """

    stem = paths["stem"]
    log_dir = paths["root"] / "logs" / "eliot"
    setup_eliot_logging(log_dir, stem)

    with eliot.start_action(
        action_type="analyse:run",
        stem=stem,
        k_factor=k_factor,
        map_cap=map_cap,
        significance_alpha=significance_alpha,
    ):
        start_time = time.time()

        try:
            if map_path:
                resolved_map = Path(map_path)
                if not resolved_map.exists():
                    raise FileNotFoundError(f"Provided map not found: {map_path}")
                run_k, run_cap = _run_from_map_location(resolved_map, k_factor, map_cap)
            else:
                resolved_map, run_cap = _resolve_map_path(paths, k_factor, map_cap)
                run_k = k_factor

            if model_path:
                resolved_model = Path(model_path)
                if not resolved_model.exists():
                    raise FileNotFoundError(f"Provided model not found: {model_path}")
            else:
                resolved_model = _resolve_model_path(paths)

            resolution = _infer_resolution(paths)
        except FileNotFoundError as exc:
            print(f"Skipping {stem}: {exc}")
            eliot.log_message(message_type="analyse:skipped", stem=stem, reason=str(exc))
            return

        out_dir = paths["root"] / "analyse_results"
        out_dir.mkdir(exist_ok=True, parents=True)

        print(
            f"--- Analysing {stem} | map: {resolved_map.name} "
            f"| model: {resolved_model.name} | resolution: {resolution:.2f} Å ---"
        )

        eliot.log_message(
            message_type="analyse:params",
            map=resolved_map.name,
            k_factor=run_k,
            map_cap=run_cap,
            model=resolved_model.name,
            resolution_angstrom=round(resolution, 3),
        )

        null_params = _load_null_params(paths, run_k, run_cap)
        significance_threshold = None
        base_config = snr_map_config()
        if null_params is not None:
            significance_threshold = compute_significance_threshold(null_params, alpha=significance_alpha)
            config = replace(
                base_config,
                aggregation=AggregationConfig(
                    opia_threshold=significance_threshold,
                    missing_density_threshold=significance_threshold,
                ),
            )
        else:
            config = base_config

        eliot.log_message(
            message_type="analyse:significance_threshold",
            threshold=significance_threshold,
            source="null_distribution" if null_params is not None else "paper_defaults",
        )

        with eliot.start_action(action_type="analyse:run_muse"):
            result = run_muse(str(resolved_map), str(resolved_model), resolution, config=config)

        export_atom_csv(result, str(out_dir / f"{stem}_atoms.csv"))
        export_residue_csv(result, str(out_dir / f"{stem}_residues.csv"))

        summary = export_summary(result)
        summary["map_path"] = str(resolved_map)
        summary["k_factor"] = run_k
        summary["map_cap"] = run_cap
        summary["significance_alpha"] = significance_alpha
        summary["significance_snr_threshold"] = significance_threshold
        with open(out_dir / f"{stem}_summary.json", "w") as fh:
            json.dump(summary, fh, indent=2)

        write_scored_pdb(result, str(resolved_model), str(out_dir / f"{stem}_scored.pdb"), score_level="atom", score_field = "score")

        elapsed = time.time() - start_time
        eliot.log_message(
            message_type="analyse:complete",
            opia=round(result.opia, 4),
            n_atoms=len(result.atom_scores),
            n_residues=len(result.residue_scores),
            elapsed_seconds=round(elapsed, 2),
            output_dir=str(out_dir),
        )
        print(
            f"Analysis results saved to {out_dir}\n"
            f"  OPIA: {result.opia:.3f} | atoms: {len(result.atom_scores)} "
            f"| residues: {len(result.residue_scores)} | time: {elapsed:.1f}s"
        )

def run_analysis(
    input_path: str,
    stem: Optional[str] = None,
    map_path: Optional[str] = None,
    model_path: Optional[str] = None,
    k_factor: float = _DEFAULT_K_FACTOR,
    map_cap: Optional[int] = _DEFAULT_MAP_CAP,
    num_processes: int = 1,
    significance_alpha: float = 0.05,
    lig_resname: str = "LIG",
    neighbourhood_radius: float = 10.0,
) -> None:
    """
    Run MUSE analysis on a single experiment or a screening directory.

    For screening runs (multiple experiments) an HTML summary report and
    per-experiment JSON files are written automatically after analysis
    completes:
        <input_path>/index.html
        <input_path>/metadata/<stem>_screen_result.json
        <input_path>/metadata/screen_summary_<timestamp>.json
    """

    input_path = Path(input_path)

    if stem:
        paths = get_experiment_paths(input_path, stem)
        paths["stem"] = stem
        _analyse_single(paths, map_path, model_path, k_factor, map_cap, significance_alpha)
        return

    experiments = list(find_experiments(str(input_path)))
    if not experiments:
        raise ValueError(
            f"No valid experiments found at {input_path}. "
            "Ensure the directory contains a 'processed/' subdirectory with a "
            "'*_updated.pdb' or '*_updated.cif' file and a corresponding "
            "'metadata/*_omission_map.json'."
        )

    if len(experiments) == 1:
        _analyse_single(experiments[0], map_path, model_path, k_factor, map_cap, significance_alpha)
    else:
        print(
            f"Screening mode: {len(experiments)} experiments found, "
            f"using {num_processes} process(es)."
        )
        worker = partial(
            _analyse_single,
            map_path=map_path,
            model_path=model_path,
            k_factor=k_factor,
            map_cap=map_cap,
            significance_alpha=significance_alpha,
        )
        with Pool(max(1, num_processes)) as pool:
            pool.map(worker, experiments)

        generate_screen_report(
            screening_dir=input_path,
            lig_resname=lig_resname,
            neighbourhood_radius=neighbourhood_radius,
        )

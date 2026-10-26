from __future__ import annotations

import json
import numpy as np
import gemmi
import eliot
from functools import partial
from multiprocessing import Pool
from pathlib import Path
from typing import Optional

import time

from common.logging import setup_eliot_logging
from quantify import ownership_logic
from quantify import aggregator

from quantify import statistical_model
from quantify.utils import (
    get_experiment_paths,
    infer_omission_mode,
    find_experiments,
    read_mtz,
)


class MapCapError(ValueError):
    """The requested map cap does not fit this structure's ensemble"""


def _map_path(results_dir: Path, stem: str, i: int) -> Path:
    return results_dir / f"{stem}_{i}" / f"{stem}_{i}.mtz"


def schedule_length(omission_map: Optional[dict]) -> Optional[int]:
    """
    Number of maps debias scheduled: highest omitted map id + 1
    """

    if not omission_map:
        return None
    ids = [i for map_ids in omission_map.values() for i in map_ids]
    return max(ids) + 1 if ids else None


def never_omitted(omission_map: Optional[dict], map_cap: int) -> list:
    """
    Owners whose omissions all fall at or beyond the cap, so their bias cannot be estimated
    """

    if not omission_map:
        return []
    return [owner for owner, ids in omission_map.items() if ids and min(ids) >= map_cap]


def _check_maps_present(results_dir: Path, stem: str, map_cap: int):
    # every row lines up with an omission schedule, so a gap cannot be skipped or zero-filled
    missing = [i for i in range(map_cap) if not _map_path(results_dir, stem, i).exists()]
    if missing:
        shown = missing if len(missing) <= 10 else missing[:10] + ["..."]
        hint = (
            f"Re-run with --map_cap {missing[0]} to use only the complete maps 0-{missing[0] - 1}, "
            if missing[0] >= 2
            else ""
        )
        raise FileNotFoundError(
            f"{len(missing)} of {map_cap} maps missing for {stem} (indices {shown}). "
            f"{hint}or regenerate the missing maps with stomp-debias."
        )


def resolve_map_cap(
    results_dir: Path, stem: str, map_cap: Optional[int], n_scheduled: Optional[int]
) -> int:
    """
    Number of maps to use for this structure. None means every scheduled map
    (or, without a schedule, every consecutive map on disk). Raises if the cap
    exceeds the schedule or any of maps 0 to cap-1 is missing.
    """

    if n_scheduled is not None and map_cap is not None and map_cap > n_scheduled:
        raise MapCapError(
            f"--map_cap {map_cap} exceeds the {n_scheduled} maps debias scheduled for {stem}. "
            f"Use --map_cap {n_scheduled} or --map_cap auto."
        )

    available = n_scheduled
    if available is None:
        available = 0
        while _map_path(results_dir, stem, available).exists():
            available += 1

    cap = available if map_cap is None else map_cap
    if cap < 2:
        raise MapCapError(f"Need at least 2 maps for {stem} to estimate noise, got {cap}.")

    _check_maps_present(results_dir, stem, cap)

    if cap < available:
        print(
            f"Note: using {cap} of {available} maps for {stem}; maps {cap}-{available - 1} are "
            "ignored, so owners omitted in them have fewer omitted samples. "
            "Use --map_cap auto to use them all."
        )
    return cap


def load_ensemble(results_dir: Path, stem: str, map_cap: Optional[int]):
    """
    Loads MTZ files into a 4D numpy array
    """

    first_path = _map_path(results_dir, stem, 0)
    if not first_path.exists():
        raise FileNotFoundError("First map not found")

    _check_maps_present(results_dir, stem, map_cap)
    map_paths = [_map_path(results_dir, stem, i) for i in range(map_cap)]

    ref_map = read_mtz(str(first_path))
    ref_grid = ref_map.grid
    shape = ref_grid.shape

    ensemble_array = np.zeros((map_cap, *shape), dtype=np.float32)
    for i, p in enumerate(map_paths):
        ensemble_array[i] = read_mtz(str(p)).grid.array

    return ensemble_array, ref_grid


def save_map(array: np.ndarray, ref_grid: gemmi.FloatGrid, output_path: Path | str):
    """
    Saves MTZ files as a ccp4 map
    """

    grid = gemmi.FloatGrid(array)
    grid.set_unit_cell(ref_grid.unit_cell)
    grid.spacegroup = ref_grid.spacegroup

    ccp4_map = gemmi.Ccp4Map()
    ccp4_map.grid = grid
    ccp4_map.update_ccp4_header()
    ccp4_map.write_ccp4_map(str(output_path))


def _quantify_single(paths: dict, force: bool, k_factor: float, map_cap: Optional[int]):
    """
    Run quantification for a single experiment defined by a paths dict
    """

    stem = paths["stem"]
    log_dir = paths["root"] / "logs" / "eliot"
    setup_eliot_logging(log_dir, stem)

    with eliot.start_action(
        action_type="quantify:run",
        stem=stem,
        k_factor=k_factor,
        map_cap=map_cap,
    ):
        start_time = time.time()

        res_ref = _map_path(paths["results_dir"], stem, 0)
        if not res_ref.exists():
            print(f"Skipping {stem}: no perturbation maps found in results directory.")
            eliot.log_message(message_type="quantify:skipped", stem=stem, reason="no_maps")
            return

        omission_map = None
        if paths["omission_json"].exists():
            omission_map = ownership_logic.load_omission_map(paths["omission_json"])
        elif k_factor != 0:
            print(f"Skipping {stem}: omission map not found.")
            eliot.log_message(message_type="quantify:skipped", stem=stem, reason="omission_json_missing")
            return

        try:
            n_scheduled = schedule_length(omission_map)
            current_map_cap = resolve_map_cap(paths["results_dir"], stem, map_cap, n_scheduled)
        except (FileNotFoundError, MapCapError) as exc:
            print(f"Skipping {stem}: {exc}")
            eliot.log_message(
                message_type="quantify:skipped",
                stem=stem,
                reason="missing_maps" if isinstance(exc, FileNotFoundError) else "map_cap_mismatch",
                detail=str(exc),
            )
            return

        unestimated = never_omitted(omission_map, current_map_cap) if k_factor != 0 else []
        if unestimated:
            print(
                f"WARNING: with --map_cap {current_map_cap}, {len(unestimated)} of {len(omission_map)} "
                f"owners of {stem} are never omitted, so their model bias is not removed "
                "and the SNR around them is biased. Raise --map_cap or use --map_cap auto."
            )
            eliot.log_message(
                message_type="quantify:warning",
                stem=stem,
                reason="owners_never_omitted",
                n_owners=len(unestimated),
                map_cap=current_map_cap,
            )

        out_dir = paths["quantify_dir"] / f"k_{k_factor}_cap_{current_map_cap}"

        if not force and (out_dir / f"{stem}_snr.ccp4").exists():
            print(f"Results exist for {stem}. Use --force to overwrite.")
            eliot.log_message(message_type="quantify:skipped", stem=stem, reason="results_exist")
            return

        print(f"--- Quantifying {stem} (K={k_factor}, maps={current_map_cap}) ---")

        mtz = gemmi.read_mtz_file(str(res_ref))
        resolution = mtz.resolution_high()
        print(f"Resolution: {resolution:.2f} Å")

        if k_factor == 0:
            spatial_index = None
            eliot.log_message(
                message_type="quantify:params",
                resolution_angstrom=round(resolution, 3),
                omission_mode="none (k=0, plain average)",
                map_cap=current_map_cap,
                n_scheduled=n_scheduled,
            )
        else:
            mode = infer_omission_mode(omission_map)

            eliot.log_message(
                message_type="quantify:params",
                resolution_angstrom=round(resolution, 3),
                omission_mode=mode,
                map_cap=current_map_cap,
                n_scheduled=n_scheduled,
            )

            with eliot.start_action(action_type="quantify:build_spatial_index"):
                spatial_index = ownership_logic.build_spatial_index(
                    paths["processed_pdb"], omission_map, resolution, k_factor, mode
                )
            if not spatial_index:
                print("Error: Spatial index failed.")
                return

        try:
            with eliot.start_action(action_type="quantify:load_ensemble", map_cap=current_map_cap):
                data, grid = load_ensemble(paths["results_dir"], stem, current_map_cap)
        except ValueError as exc:
            print(f"Skipping {stem}: {exc}")
            eliot.log_message(
                message_type="quantify:skipped",
                stem=stem,
                reason="mtz_column_error",
                detail=str(exc),
            )
            return
        except FileNotFoundError as exc:
            print(f"Skipping {stem}: {exc}")
            eliot.log_message(
                message_type="quantify:skipped",
                stem=stem,
                reason="missing_maps",
                detail=str(exc),
            )
            return

        nx, ny, nz = data.shape[1:]
        with eliot.start_action(
            action_type="quantify:aggregate_ensemble",
            grid_shape=[nx, ny, nz],
            n_voxels=nx * ny * nz,
        ):
            sig, nos, snr = aggregator.aggregate_ensemble(data, grid, spatial_index)

        out_dir.mkdir(exist_ok=True, parents=True)
        save_map(sig, grid, out_dir / f"{stem}_mean.ccp4")
        save_map(nos, grid, out_dir / f"{stem}_std.ccp4")
        save_map(snr, grid, out_dir / f"{stem}_snr.ccp4")

        print("Running statistical modeling")

        with eliot.start_action(action_type="quantify:statistical_model", n_samples=20000):
            null_samples = statistical_model.sample_null_distribution(
                snr_map=str(out_dir / f"{stem}_snr.ccp4"),
                model_path=paths["original_pdb"],
                n_samples=20000,
            )
            null_params = statistical_model.fit_null_distribution(null_samples)
            null_params_path = (
                paths["metadata_dir"]
                / f"{stem}_null_params_k{k_factor}_cap{current_map_cap}.json"
            )
            with open(null_params_path, "w") as fh:
                json.dump(null_params, fh, indent=2)

            p_value_map = statistical_model.fit_t_test(null_params, snr)
            save_map(np.array(p_value_map), grid, out_dir / f"{stem}_p_value.ccp4")

        elapsed_time = time.time() - start_time
        eliot.log_message(
            message_type="quantify:complete",
            stem=stem,
            output_dir=str(out_dir),
            elapsed_seconds=round(elapsed_time, 2),
        )
        print(f"Quantification results of the {stem} perturbation saved to {out_dir}")
        print(f"Total execution time: {elapsed_time:.2f} seconds")


def run_quantification(
    input_path: Path | str,
    stem: Optional[str] = None,
    force: bool = False,
    k_factor: float = 1.0,
    map_cap: Optional[int] = 50,
    num_processes: int = 1,
):
    input_path = Path(input_path)

    if stem:
        paths = get_experiment_paths(input_path, stem)
        paths["stem"] = stem
        _quantify_single(paths, force, k_factor, map_cap)
        return

    experiments = list(find_experiments(str(input_path)))
    if not experiments:
        raise ValueError(f"No valid experiments found at {input_path}")

    if len(experiments) == 1:
        _quantify_single(experiments[0], force, k_factor, map_cap)
    else:
        print(
            f"Screening mode: {len(experiments)} experiments found, "
            f"using {num_processes} process(es)."
        )
        worker = partial(_quantify_single, force=force, k_factor=k_factor, map_cap=map_cap)
        with Pool(max(1, num_processes)) as pool:
            pool.map(worker, experiments)

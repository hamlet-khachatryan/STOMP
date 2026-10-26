---
title: Quantify
parent: Guides
nav_order: 2
---

# Quantify Guide

The **Quantify** module analyses the ensemble of STOMP maps produced by `stomp-debias`. It separates true crystallographic signal from bias and outputs debiased CCP4 maps.

---

## Quick start

```bash
stomp-quantify --input_path /scratch/results/my_experiment
```

The command auto-detects all experiments inside the workspace. For a single crystal, point it at the crystal subdirectory:

```bash
stomp-quantify --input_path /scratch/results/my_experiment/target_5e5z
```

---

## CLI options

| Flag | Short | Default | Description                                     |
|---|---|---|-------------------------------------------------|
| `--input_path` | `-p` | *required* | Workspace root produced by `stomp-debias`.     |
| `--stem` | `-s` | auto | Explicit experiment stem (inferred if omitted). |
| `--k_factor` | `-k` | `1.0` | Radius multiplier K for atom ownership spheres. Set to `0` to skip bias removal and produce a plain ensemble average. |
| `--map_cap` | `-c` | `50` | Use maps 0 to N-1 for every structure. Pass `auto` to use each structure's full omission schedule (see [Map cap](#map-cap)). |
| `--force` | `-f` | `False` | Overwrite existing `quantify_results/`.         |

---

## Map cap

The cap N selects maps 0 to N-1 and names the output folder `k_{k}_cap_{N}`. Debias produces a different number of maps per structure (with the default omit fraction of 0.1 each iteration usually makes 10 or 11 omission batches, so 50 or 55 maps), so one number does not fit every structure in a screen:

| Cap vs. maps on disk | What happens |
|---|---|
| `auto` | Each structure uses every map in its omission schedule, e.g. `cap_55` for one structure and `cap_50` for another. |
| Below the schedule (50 of 55) | Allowed, with a note. The SNR estimate stays valid: the dropped maps come from the last omission round, so the owners omitted in them are left with one fewer omitted sample and their bias estimate is slightly noisier. Nothing is filled in. A cap so low that some owners are never omitted (below one full round) prints a WARNING, because their bias cannot be removed. |
| Above the schedule (55 of 50) | The structure is skipped. Maps beyond the schedule do not exist, and filling them with zeros would corrupt the mean, the noise and every bias estimate. |
| Gaps (scheduled map missing on disk) | The structure is skipped with the missing indices and the largest complete cap, because each map lines up with one omission pattern. |

`stomp-analyse` defaults to `--map_cap auto`, so it finds each structure's own `cap_N` folder.

---

## Python API

```python
from quantify.api import run_quantification

run_quantification(
    input_path="/scratch/results/my_experiment",
    k_factor=1.0,
    map_cap=None,  # auto: every scheduled map for each structure
    force=False,
)
```

---

## Required input layout

`stomp-quantify` expects the directory structure created by `stomp-debias`:

```
<crystal>/
├── processed/
│   └── {stem}_updated.pdb
├── metadata/
│   └── {stem}_omission_map.json
└── results/
    ├── {stem}_0/{stem}_0.mtz
    ├── {stem}_1/{stem}_1.mtz
    └── ...
```

---

## Outputs

Results are written to `<crystal>/quantify_results/k_{k}_cap_{cap}/`:

| File | Description |
|---|---|
| `{stem}_signal.ccp4` | Mean debiased density (true signal) |
| `{stem}_noise.ccp4` | Std-dev of cleaned densities (local noise) |
| `{stem}_snr.ccp4` | Signal-to-noise ratio — input to `stomp-analyse` |
| `{stem}_p_value.ccp4` | Voxel-wise significance (t-test vs bulk solvent) |

A null-distribution parameter file is also saved to `metadata/` for use by `stomp-analyse` to set a data-driven significance threshold.

---

## Algorithm overview

### Ownership

For each voxel v, atoms within distance `R(element, resolution) × k_factor` are identified as *owners*. This is determined via a KD-tree of atom positions and produces a binary status matrix **S** (shape N\_maps × N\_owners): 1 = atom present in that map, 0 = omitted.

### Bias estimation and removal

```text
For each owner j:
    if S[:,j] has both 0s and 1s:
        B_j = mean(D[S[:,j]=1]) − mean(D[S[:,j]=0])

CleanedVector = D − S · B
Signal = mean(CleanedVector)
Noise  = std(CleanedVector)
```

### Plain average mode (`k=0`)

When `--k_factor 0` is passed, ownership assignment and margianal bias removal are skipped. Each voxel is simply averaged across all maps in the ensemble:

```text
Signal = mean(D)
Noise  = std(D)
SNR    = Signal / Noise
```

---

## HPC / SLURM submission

For large screening workspaces, wrap the command in `sbatch` and use `--num_processes` to parallelise across crystals within the job:

```bash
sbatch --partition cs05r \
       --cpus-per-task 8 \
       --mem-per-cpu 5G \
       --time 3-00:00:00 \
       --wrap "stomp-quantify --input_path /scratch/results/my_screen \
                               --num_processes 8"
```

`--num_processes` controls how many crystals are processed in parallel inside the job. Set it to match `--cpus-per-task`.

---

## Parameter reference

See [Configuration Reference — Quantify](../reference#quantify-stomp-quantify).
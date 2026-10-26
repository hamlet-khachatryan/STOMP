"""
References:
    - Meyder et al. (2017) J. Chem. Inf. Model. 57, 2437-2447
    - Nittinger et al. (2015) J. Chem. Inf. Model. 55, 771-783
"""

from __future__ import annotations

from typing import Dict, List

from analyse.muse.config import AggregationConfig
from analyse.muse.scoring import AtomScore


def flag_missing_density(
    atom_scores: List[AtomScore],
    config: AggregationConfig,
) -> None:
    """
    Flag atoms where the positive-weight score is below the threshold, suggesting that the
    atom placement is unsupported

    Args:
        atom_scores: Per-atom scores whose has_missing_density fields are updated
        config: AggregationConfig carrying the threshold
    """
    threshold = config.missing_density_threshold
    for ascore in atom_scores:
        if ascore.score_positive < threshold:
            object.__setattr__(ascore, "has_missing_density", True)


def flag_unaccounted_density(
    atom_scores: List[AtomScore],
    config: AggregationConfig,
) -> None:
    """
    Flag atoms with significant negative-weight score, suggesting nearby unmodelled
    density or a misfit

    Args:
        atom_scores: Per-atom scores whose has_unaccounted_density fields are
            updated.
        config: AggregationConfig carrying the threshold
    """
    threshold = config.unaccounted_density_threshold
    for ascore in atom_scores:
        if abs(ascore.score_negative) > threshold:
            object.__setattr__(ascore, "has_unaccounted_density", True)


def run_diagnostics(
    atom_scores: List[AtomScore],
    config: AggregationConfig,
) -> None:
    """
    Calls flag_missing_density and flag_unaccounted_density
    """
    flag_missing_density(atom_scores, config)
    flag_unaccounted_density(atom_scores, config)


def summarize_diagnostics(atom_scores: List[AtomScore]) -> Dict[str, int]:
    """
    Return counts of each diagnostic flag across all atom scores

    Args:
        atom_scores: Scored atoms
    Returns:
        Dict with keys 'n_missing_density', 'n_unaccounted_density', 'n_total'.
    """
    return {
        "n_total": len(atom_scores),
        "n_missing_density": sum(1 for a in atom_scores if a.has_missing_density),
        "n_unaccounted_density": sum(
            1 for a in atom_scores if a.has_unaccounted_density
        ),
    }

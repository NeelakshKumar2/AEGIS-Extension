"""Ranking metrics. All take a ranked list of files and the set of true files."""
import random


def precision_at_k(ranked, truth, k):
    return sum(1 for f in ranked[:k] if f in truth) / k if k else 0.0


def recall_at_k(ranked, truth, k):
    return sum(1 for f in ranked[:k] if f in truth) / len(truth) if truth else 0.0


def reciprocal_rank(ranked, truth):
    for i, f in enumerate(ranked, 1):
        if f in truth:
            return 1.0 / i
    return 0.0


def scope_reduction(graph_size, k):
    """Share of the possible-impact set that need not be re-evaluated if only the top k are kept."""
    return 1.0 - min(k, graph_size) / graph_size if graph_size else 0.0


def mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs) if xs else 0.0


def bootstrap_ci(values, n=1000, seed=0, alpha=0.05):
    """Percentile bootstrap CI of the mean (resampling commits)."""
    values = list(values)
    if not values:
        return (0.0, 0.0)
    rng = random.Random(seed)
    means = sorted(mean(rng.choices(values, k=len(values))) for _ in range(n))
    return means[int(n * alpha / 2)], means[int(n * (1 - alpha / 2)) - 1]

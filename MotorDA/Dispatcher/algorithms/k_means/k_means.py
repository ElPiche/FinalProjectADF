from dataclasses import dataclass
from typing import Dict, List, Any
import numpy as np
from ...algorithm_interface import register_algorithm
from sklearn.cluster import KMeans as SKKMeans

@register_algorithm
@dataclass
class KMeans:
    """
    Multidimensional K-Means anomaly detection.

    Expects each training value to be a list of floats representing
    D-dimensional feature vectors.
    """

    __algorithm_meta__ = {
        "description": "Multidimensional K-Means anomaly detection",
        "parameters": ["n_clusters", "percentile"],
    }

    # Defaults (these can be overridden by parameters/kwargs in train call)
    n_clusters: int = 3
    percentile: float = 97.5
    supports_bucketing: bool = False  # typically KMeans used as global model, orchestrator can override
    min_training_samples: int = 20

    @property
    def name(self) -> str:
        """Algorithm identifier (e.g., 'zscore', 'k_means')."""
        ...
        return "k_means"

    @property
    def is_multi_dimensional(self) -> bool:
        """True if algorithm processes all dimensions together."""
        ...
        return True

    # ------------------------------
    # Helper: build feature matrix
    # ------------------------------
    def _build_matrix(self, observations: List[Dict[str, Any]], parameters: List[Dict[str, Any]]) -> np.ndarray:

        if not parameters:
            raise ValueError("parameters list is required and must include 'dimension' entries")

        feature_keys = [p.get("dimension") for p in parameters]
        if any(k is None for k in feature_keys):
            raise ValueError("Each parameter dict must include the 'dimension' key")

        # Build NxD matrix
        rows = []
        for obs in observations:
            try:
                row = [float(obs[k]) for k in feature_keys]
            except KeyError as e:
                raise KeyError(f"Observation missing required dimension key: {e}") from e
            rows.append(row)

        X = np.array(rows, dtype=float)
        return X

    # ------------------------------
    # TRAIN (multi-dimensional)
    # ------------------------------
    def train_multi_dimensional(
        self,
        observations: List[Dict[str, Any]],
        parameters: List[Dict[str, Any]],
        **kwargs
    ) -> Dict[str, Any]:
        """
        Train KMeans on the provided observations.

        Returns a JSON-serializable model dict:
            {
              "centroids": [[...], [...], ...],
              "n_clusters": int,
              "percentile": float,
              "threshold": float,                  # global threshold if cluster_specific=False
              "cluster_thresholds": [f1, f2, ...], # present if cluster_specific=True
              "feature_order": ["cpu", "mem", ...],
              "training_sample_count": N
            }
        """
        if not observations or len(observations) < 1:
            raise ValueError("observations must be a non-empty list")

        # hyperparams
        n_clusters = int(kwargs.get("n_clusters", 3))
        percentile = float(kwargs.get("percentile", 97.5))
        cluster_specific = bool(kwargs.get("cluster_specific", False))

        # build matrix NxD
        X = self._build_matrix(observations, parameters)
        n_samples = X.shape[0]

        if n_samples < 1:
            raise ValueError("No valid training samples found after building matrix")

        if n_samples < self.min_training_samples:
            # still allow training but warn (caller/orchestrator may check min_training_samples)
            # we don't have logger here by contract, raise only if desired - keep permissive
            pass

        # Fit KMeans
        model = SKKMeans(n_clusters=n_clusters, n_init="auto")
        model.fit(X)

        centroids = model.cluster_centers_  # shape (k, d)
        labels = model.labels_              # shape (n,)

        # compute Euclidean distances to assigned centroids
        distances = np.linalg.norm(X - centroids[labels], axis=1)

        # global threshold
        global_threshold = float(np.percentile(distances, percentile))

        result: Dict[str, Any] = {
            "centroids": centroids.tolist(), # might be interesting to save the dimension name inside this list
            "n_clusters": n_clusters,
            "percentile": percentile,
            "threshold": global_threshold,
            "feature_order": [p["dimension"] for p in parameters],
            "training_sample_count": int(n_samples),
        }

        if cluster_specific:
            # compute percentile per-cluster
            cluster_thresholds = []
            for c in range(n_clusters):
                ds = distances[labels == c]
                if ds.size == 0:
                    # no points assigned to this centroid in training; set threshold 0
                    cluster_thresholds.append(0.0)
                else:
                    cluster_thresholds.append(float(np.percentile(ds, percentile)))
            result["cluster_thresholds"] = cluster_thresholds

        return result

    # ------------------------------
    # DETECT (multi-dimensional)
    # ------------------------------
    def detect_multi_dimensional(
        self,
        observation: Dict[str, Any],
        model: Dict[str, Any],
        parameters: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Detect anomaly for a single observation dict using the trained model.

        Returns:
            {
              "is_anomaly": bool,
              "distance": float,
              "assigned_cluster": int,
              "threshold": float,
              "cluster_thresholds": [...],  # optional
              "feature_vector": [...],
            }
        """
        # Validate model and parameters
        if "centroids" not in model:
            raise ValueError("Model missing 'centroids'")

        centroids = np.array(model["centroids"], dtype=float)  # (k, d)
        feature_order = model.get("feature_order")
        if not feature_order:
            # fallback: use parameters order
            feature_order = [p["dimension"] for p in parameters]

        # build feature vector in same order
        try:
            x = np.array([float(observation[k]) for k in feature_order], dtype=float)
        except KeyError as e:
            raise KeyError(f"Observation missing required dimension key: {e}") from e

        # distances to all centroids
        dists = np.linalg.norm(centroids - x.reshape(1, -1), axis=1)
        assigned = int(np.argmin(dists))
        distance = float(dists[assigned])

        # choose threshold: cluster-specific if available, else model["threshold"]
        chosen_threshold = float(model.get("threshold", 0.0))
        cluster_thresholds = model.get("cluster_thresholds")
        if cluster_thresholds:
            # safe-guard lengths
            if assigned < len(cluster_thresholds):
                chosen_threshold = float(cluster_thresholds[assigned])

        is_anomaly = distance > chosen_threshold

        return {
            "is_anomaly": bool(is_anomaly),
            "distance": distance,
            "assigned_cluster": assigned,
            "threshold": chosen_threshold,
            "cluster_thresholds": cluster_thresholds if cluster_thresholds is not None else None,
            "feature_vector": x.tolist(),
        }

    # Optional convenience: batch detection (not required by register for multi-dim,
    # but sometimes handy)
    def detect_multi_dimensional_batch(
        self,
        observations: List[Dict[str, Any]],
        model: Dict[str, Any],
        parameters: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        return [self.detect_multi_dimensional(o, model, parameters) for o in observations]



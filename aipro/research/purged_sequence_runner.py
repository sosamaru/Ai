"""Bounded optional sequence-model training on purged PAPER folds.

PyTorch and TensorFlow remain lazy optional dependencies. Every fold receives a
fresh model, train-only scaling, contiguous partition-local sequences, and
deterministic evidence. The runner never persists models, contacts brokers,
submits orders, promotes a champion, or grants execution authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import math
from typing import Any, Callable, Mapping, Protocol, Sequence

from aipro.intelligence.classical_ml import (
    CandidateFamily,
    CandidateSpec,
    EvaluationPolicy,
    FoldMetrics,
    ModelDomain,
    evaluate_candidate,
)
from aipro.intelligence.optional_sequence_backends import (
    SequenceModelSpec,
    ValidatedSequenceSpec,
    load_backend,
    validate_sequence_spec,
)
from aipro.research.purged_training_runner import (
    PurgedFoldTrainingEvidence,
    PurgedTrainingReport,
    TrainingRow,
    _score_fold,
    _validate_rows,
)
from aipro.research.purged_walk_forward import (
    Observation,
    PurgedWalkForwardSplitter,
    WalkForwardConfig,
    assert_no_leakage,
)


class SequenceTrainer(Protocol):
    def fit(
        self,
        x: Sequence[Sequence[Sequence[float]]],
        y: Sequence[int],
    ) -> None: ...

    def predict_proba(
        self,
        x: Sequence[Sequence[Sequence[float]]],
    ) -> Sequence[float]: ...


TrainerFactory = Callable[[ValidatedSequenceSpec, int], SequenceTrainer]


@dataclass(frozen=True)
class SequenceTrainingConfig:
    spec: SequenceModelSpec
    decision_threshold: float = 0.5
    estimated_round_trip_cost_bps: float = 5.0
    max_train_sequences: int = 50_000
    max_test_sequences: int = 20_000
    max_feature_values_per_fold: int = 25_000_000

    def __post_init__(self) -> None:
        if not 0.0 < self.decision_threshold < 1.0:
            raise ValueError("decision_threshold must be in (0, 1)")
        if (
            not math.isfinite(self.estimated_round_trip_cost_bps)
            or self.estimated_round_trip_cost_bps < 0.0
        ):
            raise ValueError(
                "estimated_round_trip_cost_bps must be finite and non-negative"
            )
        for name in ("max_train_sequences", "max_test_sequences"):
            value = getattr(self, name)
            if not 1 <= value <= 1_000_000:
                raise ValueError(f"{name} must be in [1, 1000000]")
        if not 1 <= self.max_feature_values_per_fold <= 250_000_000:
            raise ValueError(
                "max_feature_values_per_fold must be in [1, 250000000]"
            )


@dataclass(frozen=True)
class _ScoringConfig:
    decision_threshold: float
    estimated_round_trip_cost_bps: float


@dataclass(frozen=True)
class _SequenceExample:
    target_row: TrainingRow
    values: tuple[tuple[float, ...], ...]


def run_purged_sequence_training(
    rows: Sequence[TrainingRow],
    *,
    feature_names: Sequence[str],
    walk_forward: WalkForwardConfig,
    training: SequenceTrainingConfig,
    evaluation_policy: EvaluationPolicy | None = None,
    trainer_factory: TrainerFactory | None = None,
) -> PurgedTrainingReport:
    """Fit and score one optional sequence candidate across purged folds."""

    names = tuple(feature_names)
    ordered = _validate_rows(rows, names)
    domain = ordered[0].domain
    validated = validate_sequence_spec(training.spec)
    _validate_training_identity(validated, domain, names)

    sequence_length = int(validated.normalized_parameters["sequence_length"])
    observations = tuple(
        Observation(row.index, row.label_start, row.label_end, row.domain.value)
        for row in ordered
    )
    folds = PurgedWalkForwardSplitter(walk_forward).split(observations)
    by_index = {row.index: row for row in ordered}
    factory = trainer_factory or _default_trainer_factory
    evidence: list[PurgedFoldTrainingEvidence] = []
    metrics: list[FoldMetrics] = []
    scoring = _ScoringConfig(
        decision_threshold=training.decision_threshold,
        estimated_round_trip_cost_bps=training.estimated_round_trip_cost_bps,
    )

    for fold in folds:
        assert_no_leakage(fold, observations)
        train_examples = _build_partition_sequences(
            by_index, fold.train_indices, sequence_length
        )
        test_examples = _build_partition_sequences(
            by_index, fold.test_indices, sequence_length
        )
        _validate_fold_budget(train_examples, test_examples, training, len(names))
        if len({example.target_row.target for example in train_examples}) < 2:
            raise ValueError("each sequence training fold requires both target classes")

        means, scales = _fit_sequence_scaler(train_examples, len(names))
        x_train = tuple(
            _scale_sequence(example.values, means, scales)
            for example in train_examples
        )
        x_test = tuple(
            _scale_sequence(example.values, means, scales)
            for example in test_examples
        )
        y_train = tuple(example.target_row.target for example in train_examples)

        trainer = factory(validated, len(names))
        trainer.fit(x_train, y_train)
        probabilities = _validate_probabilities(
            trainer.predict_proba(x_test), len(x_test)
        )
        test_rows = tuple(example.target_row for example in test_examples)
        fold_metrics = _score_fold(test_rows, probabilities, scoring)
        metrics.append(fold_metrics)
        model_fingerprint = _fold_model_fingerprint(
            validated=validated,
            fold_fingerprint=fold.fingerprint,
            means=means,
            scales=scales,
            probabilities=probabilities,
        )
        evidence.append(
            PurgedFoldTrainingEvidence(
                fold_fingerprint=fold.fingerprint,
                train_count=len(train_examples),
                test_count=len(test_examples),
                purged_count=len(fold.purged_indices),
                embargoed_count=len(fold.embargoed_indices),
                balanced_accuracy=fold_metrics.balanced_accuracy,
                brier_score=fold_metrics.brier_score,
                expected_value_bps=fold_metrics.expected_value_bps,
                turnover=fold_metrics.turnover,
                model_fingerprint=model_fingerprint,
            )
        )

    candidate_spec = CandidateSpec(
        name=validated.spec.name,
        family=CandidateFamily.SEQUENCE_MODEL,
        domain=domain,
        feature_names=names,
        target_name=validated.spec.target_name,
        random_seed=validated.spec.seed,
        parameters={
            "backend": validated.spec.backend,
            "model_family": validated.spec.model_family,
            **dict(validated.normalized_parameters),
            "decision_threshold": training.decision_threshold,
            "estimated_round_trip_cost_bps": (
                training.estimated_round_trip_cost_bps
            ),
            "validation": "purged_walk_forward",
            "sequence_partition_policy": "strict_partition_local",
        },
    )
    evaluation = evaluate_candidate(candidate_spec, metrics, evaluation_policy)
    payload = {
        "domain": domain.value,
        "candidate_name": validated.spec.name,
        "sequence_spec_fingerprint": validated.fingerprint,
        "folds": [item.__dict__ for item in evidence],
        "evaluation_fingerprint": evaluation.fingerprint,
        "paper_only": True,
        "grants_execution_authority": False,
    }
    fingerprint = sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return PurgedTrainingReport(
        domain=domain,
        candidate_name=validated.spec.name,
        folds=tuple(evidence),
        evaluation=evaluation,
        fingerprint=fingerprint,
    )


def _validate_training_identity(
    validated: ValidatedSequenceSpec,
    domain: ModelDomain,
    feature_names: tuple[str, ...],
) -> None:
    if validated.spec.domain != domain.value:
        raise ValueError("sequence specification domain does not match training rows")
    if tuple(validated.spec.feature_names) != feature_names:
        raise ValueError(
            "sequence specification feature_names must exactly match training features"
        )


def _build_partition_sequences(
    by_index: Mapping[int, TrainingRow],
    allowed_indices: Sequence[int],
    sequence_length: int,
) -> tuple[_SequenceExample, ...]:
    allowed = frozenset(allowed_indices)
    examples: list[_SequenceExample] = []
    for target_index in sorted(allowed):
        start = target_index - sequence_length + 1
        window_indices = tuple(range(start, target_index + 1))
        if start < 0 or any(index not in allowed for index in window_indices):
            continue
        rows = tuple(by_index[index] for index in window_indices)
        examples.append(
            _SequenceExample(
                target_row=rows[-1],
                values=tuple(row.features for row in rows),
            )
        )
    if not examples:
        raise ValueError(
            "fold has no contiguous partition-local sequences; increase fold sizes "
            "or reduce sequence_length"
        )
    return tuple(examples)


def _validate_fold_budget(
    train_examples: Sequence[_SequenceExample],
    test_examples: Sequence[_SequenceExample],
    config: SequenceTrainingConfig,
    feature_width: int,
) -> None:
    if len(train_examples) > config.max_train_sequences:
        raise ValueError("training sequence count exceeds configured fold budget")
    if len(test_examples) > config.max_test_sequences:
        raise ValueError("test sequence count exceeds configured fold budget")
    sequence_length = len(train_examples[0].values)
    value_count = (
        len(train_examples) + len(test_examples)
    ) * sequence_length * feature_width
    if value_count > config.max_feature_values_per_fold:
        raise ValueError("sequence feature values exceed configured fold budget")


def _fit_sequence_scaler(
    examples: Sequence[_SequenceExample],
    feature_width: int,
) -> tuple[tuple[float, ...], tuple[float, ...]]:
    count = len(examples) * len(examples[0].values)
    means = tuple(
        sum(
            step[feature]
            for example in examples
            for step in example.values
        )
        / count
        for feature in range(feature_width)
    )
    scales: list[float] = []
    for feature, mean in enumerate(means):
        variance = (
            sum(
                (step[feature] - mean) ** 2
                for example in examples
                for step in example.values
            )
            / count
        )
        scales.append(max(math.sqrt(variance), 1e-12))
    return means, tuple(scales)


def _scale_sequence(
    values: Sequence[Sequence[float]],
    means: Sequence[float],
    scales: Sequence[float],
) -> tuple[tuple[float, ...], ...]:
    return tuple(
        tuple(
            (value - mean) / scale
            for value, mean, scale in zip(step, means, scales)
        )
        for step in values
    )


def _validate_probabilities(
    raw: Sequence[float],
    expected_count: int,
) -> tuple[float, ...]:
    probabilities = tuple(float(value) for value in raw)
    if len(probabilities) != expected_count:
        raise ValueError("sequence probability count does not match test sequences")
    if any(
        not math.isfinite(value) or not 0.0 <= value <= 1.0
        for value in probabilities
    ):
        raise ValueError("sequence probabilities must be finite and in [0, 1]")
    return probabilities


def _default_trainer_factory(
    validated: ValidatedSequenceSpec,
    feature_width: int,
) -> SequenceTrainer:
    backend = load_backend(validated)
    if validated.spec.backend == "torch":
        return _TorchSequenceTrainer(backend, validated, feature_width)
    if validated.spec.backend == "tensorflow":
        return _TensorFlowSequenceTrainer(backend, validated, feature_width)
    raise ValueError(f"unsupported sequence backend: {validated.spec.backend}")


class _TorchSequenceTrainer:
    def __init__(
        self,
        torch: Any,
        validated: ValidatedSequenceSpec,
        feature_width: int,
    ) -> None:
        self._torch = torch
        self._validated = validated
        self._feature_width = feature_width
        self._model = self._build_model()

    def _build_model(self) -> Any:
        torch = self._torch
        params = self._validated.normalized_parameters
        family = self._validated.spec.model_family
        seed = self._validated.spec.seed
        torch.manual_seed(seed)
        if hasattr(torch, "set_num_threads"):
            torch.set_num_threads(1)
        if hasattr(torch, "use_deterministic_algorithms"):
            torch.use_deterministic_algorithms(True)

        nn = torch.nn
        hidden_size = int(params["hidden_size"])
        num_layers = int(params["num_layers"])
        dropout = float(params["dropout"])
        sequence_length = int(params["sequence_length"])
        feature_width = self._feature_width
        attention_heads = int(params["attention_heads"])

        class _Network(nn.Module):
            def __init__(self) -> None:
                super().__init__()
                self.family = family
                if family in {"lstm", "gru"}:
                    recurrent = nn.LSTM if family == "lstm" else nn.GRU
                    self.core = recurrent(
                        input_size=feature_width,
                        hidden_size=hidden_size,
                        num_layers=num_layers,
                        dropout=dropout if num_layers > 1 else 0.0,
                        batch_first=True,
                    )
                    self.projection = None
                    self.register_buffer("position", None)
                else:
                    self.projection = nn.Linear(feature_width, hidden_size)
                    layer = nn.TransformerEncoderLayer(
                        d_model=hidden_size,
                        nhead=attention_heads,
                        dim_feedforward=hidden_size * 2,
                        dropout=dropout,
                        activation="gelu",
                        batch_first=True,
                    )
                    self.core = nn.TransformerEncoder(layer, num_layers=num_layers)
                    position = _torch_sinusoidal_position(
                        torch, sequence_length, hidden_size
                    )
                    self.register_buffer("position", position)
                self.output = nn.Linear(hidden_size, 1)

            def forward(self, values: Any) -> Any:
                if self.family in {"lstm", "gru"}:
                    encoded, _ = self.core(values)
                else:
                    encoded = self.projection(values) + self.position
                    encoded = self.core(encoded)
                return self.output(encoded[:, -1, :]).squeeze(-1)

        return _Network()

    def fit(
        self,
        x: Sequence[Sequence[Sequence[float]]],
        y: Sequence[int],
    ) -> None:
        torch = self._torch
        params = self._validated.normalized_parameters
        features = torch.tensor(x, dtype=torch.float32)
        targets = torch.tensor(y, dtype=torch.float32)
        optimizer = torch.optim.Adam(
            self._model.parameters(),
            lr=float(params["learning_rate"]),
        )
        loss_fn = torch.nn.BCEWithLogitsLoss()
        batch_size = int(params["batch_size"])
        self._model.train()
        for _ in range(int(params["epochs"])):
            for start in range(0, len(features), batch_size):
                stop = min(len(features), start + batch_size)
                optimizer.zero_grad()
                logits = self._model(features[start:stop])
                loss = loss_fn(logits, targets[start:stop])
                loss.backward()
                optimizer.step()

    def predict_proba(
        self,
        x: Sequence[Sequence[Sequence[float]]],
    ) -> Sequence[float]:
        torch = self._torch
        features = torch.tensor(x, dtype=torch.float32)
        self._model.eval()
        with torch.no_grad():
            probabilities = torch.sigmoid(self._model(features))
        return tuple(float(value) for value in probabilities.cpu().tolist())


class _TensorFlowSequenceTrainer:
    def __init__(
        self,
        tensorflow: Any,
        validated: ValidatedSequenceSpec,
        feature_width: int,
    ) -> None:
        self._tf = tensorflow
        self._validated = validated
        self._feature_width = feature_width
        self._model = self._build_model()

    def _build_model(self) -> Any:
        tf = self._tf
        params = self._validated.normalized_parameters
        family = self._validated.spec.model_family
        tf.keras.backend.clear_session()
        tf.keras.utils.set_random_seed(self._validated.spec.seed)
        try:
            tf.config.threading.set_intra_op_parallelism_threads(1)
            tf.config.threading.set_inter_op_parallelism_threads(1)
        except RuntimeError:
            pass
        deterministic = getattr(tf.config.experimental, "enable_op_determinism", None)
        if callable(deterministic):
            deterministic()

        sequence_length = int(params["sequence_length"])
        hidden_size = int(params["hidden_size"])
        num_layers = int(params["num_layers"])
        dropout = float(params["dropout"])
        inputs = tf.keras.Input(
            shape=(sequence_length, self._feature_width),
            dtype="float32",
        )
        values = inputs
        if family in {"lstm", "gru"}:
            recurrent = (
                tf.keras.layers.LSTM
                if family == "lstm"
                else tf.keras.layers.GRU
            )
            for layer_index in range(num_layers):
                values = recurrent(
                    hidden_size,
                    dropout=dropout,
                    return_sequences=layer_index < num_layers - 1,
                )(values)
        else:
            values = tf.keras.layers.Dense(hidden_size)(values)
            positions = tf.range(start=0, limit=sequence_length, delta=1)
            position_embedding = tf.keras.layers.Embedding(
                input_dim=sequence_length,
                output_dim=hidden_size,
            )(positions)
            values = values + position_embedding
            heads = int(params["attention_heads"])
            for _ in range(num_layers):
                attention = tf.keras.layers.MultiHeadAttention(
                    num_heads=heads,
                    key_dim=hidden_size // heads,
                    dropout=dropout,
                )(values, values)
                values = tf.keras.layers.LayerNormalization(epsilon=1e-6)(
                    values + attention
                )
                feed_forward = tf.keras.layers.Dense(
                    hidden_size * 2,
                    activation="gelu",
                )(values)
                feed_forward = tf.keras.layers.Dense(hidden_size)(feed_forward)
                values = tf.keras.layers.LayerNormalization(epsilon=1e-6)(
                    values + feed_forward
                )
            values = values[:, -1, :]
        outputs = tf.keras.layers.Dense(1)(values)
        model = tf.keras.Model(inputs=inputs, outputs=outputs)
        model.compile(
            optimizer=tf.keras.optimizers.Adam(
                learning_rate=float(params["learning_rate"])
            ),
            loss=tf.keras.losses.BinaryCrossentropy(from_logits=True),
        )
        return model

    def fit(
        self,
        x: Sequence[Sequence[Sequence[float]]],
        y: Sequence[int],
    ) -> None:
        params = self._validated.normalized_parameters
        self._model.fit(
            x,
            y,
            epochs=int(params["epochs"]),
            batch_size=int(params["batch_size"]),
            shuffle=False,
            verbose=0,
        )

    def predict_proba(
        self,
        x: Sequence[Sequence[Sequence[float]]],
    ) -> Sequence[float]:
        tf = self._tf
        logits = self._model.predict(
            x,
            batch_size=int(self._validated.normalized_parameters["batch_size"]),
            verbose=0,
        )
        probabilities = tf.math.sigmoid(logits)
        flattened = tf.reshape(probabilities, (-1,))
        return tuple(float(value) for value in flattened.numpy().tolist())


def _torch_sinusoidal_position(
    torch: Any,
    sequence_length: int,
    hidden_size: int,
) -> Any:
    position = torch.arange(sequence_length, dtype=torch.float32).unsqueeze(1)
    divisor = torch.exp(
        torch.arange(0, hidden_size, 2, dtype=torch.float32)
        * (-math.log(10_000.0) / hidden_size)
    )
    encoding = torch.zeros(sequence_length, hidden_size, dtype=torch.float32)
    encoding[:, 0::2] = torch.sin(position * divisor)
    if hidden_size > 1:
        encoding[:, 1::2] = torch.cos(
            position * divisor[: encoding[:, 1::2].shape[1]]
        )
    return encoding.unsqueeze(0)


def _fold_model_fingerprint(
    *,
    validated: ValidatedSequenceSpec,
    fold_fingerprint: str,
    means: Sequence[float],
    scales: Sequence[float],
    probabilities: Sequence[float],
) -> str:
    payload = {
        "sequence_spec_fingerprint": validated.fingerprint,
        "fold_fingerprint": fold_fingerprint,
        "means": [round(value, 15) for value in means],
        "scales": [round(value, 15) for value in scales],
        "probabilities": [round(value, 15) for value in probabilities],
    }
    return sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()

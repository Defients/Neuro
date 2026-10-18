from dataclasses import dataclass, field, asdict
import time


@dataclass
class Source:
    id: str
    kind: str
    name: str
    channels: list[str]
    units: list[str]
    nominal_rate: float
    clock_domain: str
    simulated: bool = False
    metadata: dict = field(default_factory=dict)

    def to_dict(self):
        return asdict(self)


@dataclass
class Sample:
    timestamp: float
    values: list[float]
    counter: int | None = None
    interpolated: bool = False
    metadata: dict = field(default_factory=dict)
    received_at: float = field(default_factory=time.time)
    discontinuity: str | None = None

    def to_dict(self):
        return asdict(self)

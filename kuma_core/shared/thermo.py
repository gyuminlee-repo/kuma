"""The single boundary between kuma and its thermodynamic engine.

Every nearest-neighbour Tm and every secondary-structure calculation kuma
performs goes through the four functions below, so ``import primer3`` appears
in exactly one production module. Swapping the engine is then a change to this
file rather than a sweep across kuro and mame.

Deliberately thin. Each function forwards the sequence and whatever keywords
the caller supplies and returns what the engine returns. It declares no
defaults of its own: the callers already disagree about parameters on purpose
(the design scale is enzyme independent and fixed, the annealing and MAME
barcode paths use each polymerase profile's own buffer, and the NEB calibration
passes a reference config read from a JSON table), and a default here would
either flatten that or quietly duplicate the engine's own defaults. Whatever
keywords are not passed keep the engine's behaviour, exactly as before.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

import primer3


@runtime_checkable
class ThermoStructure(Protocol):
    """What kuma reads off a secondary-structure result.

    ``structure_found`` says whether a duplex or hairpin was predicted at all;
    ``tm`` (degrees Celsius), ``dg`` and ``dh`` (cal/mol, the engine's native
    units) are meaningless when it is false, and every caller guards on it.
    """

    @property
    def tm(self) -> float: ...

    @property
    def dg(self) -> float: ...

    @property
    def dh(self) -> float: ...

    @property
    def structure_found(self) -> bool: ...


def calc_tm(seq: str, **params: Any) -> float:
    """Nearest-neighbour melting temperature of ``seq`` in degrees Celsius."""
    return primer3.calc_tm(seq, **params)


def calc_hairpin(seq: str, **params: Any) -> ThermoStructure:
    """Most stable hairpin ``seq`` can form with itself."""
    return primer3.calc_hairpin(seq, **params)


def calc_homodimer(seq: str, **params: Any) -> ThermoStructure:
    """Most stable duplex two copies of ``seq`` can form."""
    return primer3.calc_homodimer(seq, **params)


def calc_heterodimer(seq1: str, seq2: str, **params: Any) -> ThermoStructure:
    """Most stable duplex ``seq1`` and ``seq2`` can form with each other."""
    return primer3.calc_heterodimer(seq1, seq2, **params)

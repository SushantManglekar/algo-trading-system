"""Bounded raw-tick series for responsive intraday line charts."""

from __future__ import annotations

from collections.abc import Sequence
from math import floor

from market_data.types import MarketTick


def downsample_ticks(ticks: Sequence[MarketTick], max_points: int) -> tuple[MarketTick, ...]:
    """Keep a representative, ordered tick series without losing its endpoints.

    Largest-triangle-three-buckets preserves visible price turns much better than a
    simple every-Nth-tick sample, while putting a strict bound on browser payload
    and SVG work.  ``TickStore.list_ticks`` already guarantees chronological order.
    """
    if max_points < 3:
        raise ValueError("max_points must be at least 3")
    if len(ticks) <= max_points:
        return tuple(ticks)

    bucket_width = (len(ticks) - 2) / (max_points - 2)
    selected: list[MarketTick] = [ticks[0]]
    previous_index = 0

    for bucket in range(max_points - 2):
        average_start = min(floor((bucket + 1) * bucket_width) + 1, len(ticks) - 1)
        average_end = min(floor((bucket + 2) * bucket_width) + 1, len(ticks))
        average_bucket = ticks[average_start:average_end] or (ticks[-1],)
        average_time = sum(item.timestamp.timestamp() for item in average_bucket) / len(
            average_bucket
        )
        average_price = sum(float(item.price) for item in average_bucket) / len(average_bucket)

        candidate_start = min(floor(bucket * bucket_width) + 1, len(ticks) - 2)
        candidate_end = min(floor((bucket + 1) * bucket_width) + 1, len(ticks) - 1)
        if candidate_end <= candidate_start:
            candidate_end = candidate_start + 1

        previous = ticks[previous_index]
        previous_time = previous.timestamp.timestamp()
        previous_price = float(previous.price)
        largest_area = -1.0
        chosen_index = candidate_start
        for index in range(candidate_start, candidate_end):
            candidate = ticks[index]
            area = abs(
                (previous_time - average_time) * (float(candidate.price) - previous_price)
                - (previous_time - candidate.timestamp.timestamp()) * (average_price - previous_price)
            )
            if area > largest_area:
                largest_area = area
                chosen_index = index

        selected.append(ticks[chosen_index])
        previous_index = chosen_index

    selected.append(ticks[-1])
    return tuple(selected)

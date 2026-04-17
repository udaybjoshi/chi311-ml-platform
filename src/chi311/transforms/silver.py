"""Silver-layer transforms.

The SCD2 table itself is produced by DLT's ``APPLY CHANGES INTO``, so we
don't reimplement that here — it's CDC machinery, not business logic.
What IS business logic is the projection that turns the SCD2 table into
the ``silver_current_311_requests`` view used by Gold, including the
``resolution_hours`` derivation.
"""
from __future__ import annotations

from pyspark.sql import DataFrame, functions as F


def current_from_scd2(scd2: DataFrame) -> DataFrame:
    """Project the SCD2 table to the current-state view.

    Filters to rows where ``__END_AT IS NULL`` (current version) and adds
    derived fields used by Gold:
      - ``resolution_hours``: hours between created_date and closed_date
        (NULL if still open).
      - ``valid_from`` / ``valid_to``: renamed SCD2 effective timestamps.
    """
    resolution_hours = F.when(
        F.col("closed_date").isNotNull(),
        (F.col("closed_date").cast("long") - F.col("created_date").cast("long")) / 3600.0,
    )

    return (
        scd2.where(F.col("__END_AT").isNull())
        .select(
            "sr_number",
            "created_date",
            "closed_date",
            "last_modified_date",
            "sr_type",
            "sr_short_code",
            "owner_department",
            "status",
            "ward",
            "community_area",
            "street_address",
            "zip_code",
            "latitude",
            "longitude",
            "origin",
            "is_duplicate",
            "is_legacy",
            "is_info_call",
            resolution_hours.alias("resolution_hours"),
            F.col("__START_AT").alias("valid_from"),
            F.col("__END_AT").alias("valid_to"),
        )
    )

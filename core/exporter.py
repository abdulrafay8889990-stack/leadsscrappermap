"""Export collected leads to CSV or Excel using pandas."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from core.models import COLUMN_TITLES, COLUMNS, Lead


def export_leads(leads: list[Lead], path: str | Path) -> int:
    """Write `leads` to `path`. The extension (.xlsx or .csv) picks the format.

    Returns the number of rows written.
    """
    path = Path(path)
    df = pd.DataFrame([lead.to_dict() for lead in leads], columns=COLUMNS)
    df = df.rename(columns=COLUMN_TITLES)

    if path.suffix.lower() == ".xlsx":
        from openpyxl.utils import get_column_letter

        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Leads")
            sheet = writer.sheets["Leads"]
            sheet.freeze_panes = "A2"
            # Size each column to its longest value (capped so URLs don't explode the sheet).
            for idx, column in enumerate(df.columns, start=1):
                longest = max([len(str(column))] + [len(str(v)) for v in df[column]])
                sheet.column_dimensions[get_column_letter(idx)].width = min(longest + 2, 60)
    else:
        # utf-8-sig adds a BOM so Excel opens accented characters correctly.
        df.to_csv(path, index=False, encoding="utf-8-sig")

    return len(df)

from __future__ import annotations

from datetime import date, datetime

from nxus_qbd.models import AdditionalNote, Check


def test_additional_note_accepts_naive_datetime_string():
    note = AdditionalNote(date="2026-01-30T00:00:00", note="hello")

    assert isinstance(note.date, date)
    assert note.date == date(2026, 1, 30)


def test_check_accepts_date_only_transaction_date():
    check = Check(
        id="txn-1",
        created_at="2026-04-08T00:00:00Z",
        updated_at="2026-04-08T00:00:00Z",
        revision_number="1",
        transaction_date="2026-01-30",
    )

    assert isinstance(check.transaction_date, date)
    assert check.transaction_date == date(2026, 1, 30)

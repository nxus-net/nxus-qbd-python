from __future__ import annotations

from datetime import date, datetime

from nxus_qbd.models import AdditionalNote, Check, CreateBillRequest

from ._model_payloads import complete_model_payload


def test_additional_note_accepts_naive_datetime_string():
    note = AdditionalNote.model_validate(
        complete_model_payload(
            AdditionalNote,
            date="2026-01-30T00:00:00",
            note="hello",
        )
    )

    assert isinstance(note.date, date)
    assert note.date == date(2026, 1, 30)


def test_check_accepts_date_only_transaction_date():
    check = Check.model_validate(
        complete_model_payload(
            Check,
            id="txn-1",
            createdAt="2026-04-08T00:00:00Z",
            updatedAt="2026-04-08T00:00:00Z",
            revisionNumber="1",
            transactionDate="2026-01-30",
        )
    )

    assert isinstance(check.transaction_date, date)
    assert check.transaction_date == date(2026, 1, 30)


def test_create_bill_accepts_date_with_source_string_length_constraint():
    bill = CreateBillRequest.model_validate(
        {
            "vendorId": "vendor-1",
            "transactionDate": "2026-04-27",
        }
    )

    assert isinstance(bill.transaction_date, date)
    assert bill.transaction_date == date(2026, 4, 27)

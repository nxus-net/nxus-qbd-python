from __future__ import annotations

from nxus_qbd.models import DataExtDef
from nxus_qbd.resources import _parse_list_items


def test_data_ext_def_accepts_missing_id_and_format_string():
    definition = DataExtDef.model_validate(
        {
            "id": None,
            "ownerId": "{C3AA84E0-D242-47AB-A12B-3EDA3A2590A2}",
            "name": "Private SDK Field",
            "type": "STR255TYPE",
            "assignToObjects": ["OtherName"],
            "listRequire": False,
            "transactionRequire": False,
            "formatString": None,
        }
    )

    assert definition.id is None
    assert definition.format_string is None


def test_flat_definition_list_is_parsed_into_models():
    parsed = _parse_list_items(
        [
            {
                "id": None,
                "ownerId": "{C3AA84E0-D242-47AB-A12B-3EDA3A2590A2}",
                "name": "Private SDK Field",
                "type": "STR255TYPE",
                "assignToObjects": ["OtherName"],
                "listRequire": False,
                "transactionRequire": False,
                "formatString": None,
            }
        ],
        DataExtDef,
    )

    assert isinstance(parsed[0], DataExtDef)
    assert parsed[0].name == "Private SDK Field"

import pytest
from pipeline.clean_orders import clean_order, parse_olist_time, read_orders, check_batch, count_oddities
from datetime import datetime, timezone


def make_row(**changes) -> dict:
    row = {
        "order_id": "a1",
        "customer_id": "c1",
        "order_status": "delivered",
        "order_purchase_timestamp": "2017-10-02 10:56:33",
        "order_approved_at": "2017-10-02 11:07:15",
        "order_delivered_carrier_date": "2017-10-04 19:55:00",
        "order_delivered_customer_date": "2017-10-10 21:25:13",
        "order_estimated_delivery_date": "2017-10-18 00:00:00",
    }
    row.update(changes)
    return row


def test_clean_order_valid_row_is_cleaned():
    clean = clean_order(make_row(order_status=" Delivered "))
    assert clean["order_status"] == "delivered"
    assert len(clean) == 8
    assert clean["order_purchase_timestamp"] == datetime(
        2017, 10, 2, 13, 56, 33, tzinfo=timezone.utc)


def test_clean_unknown_status_is_rejected():
    with pytest.raises(ValueError, match="Unknown order_status"):
        clean_order(make_row(order_status="lost"))


@pytest.mark.parametrize("column", ["order_id", "customer_id"])
def test_clean_empty_order_id_is_rejected(column):
    with pytest.raises(ValueError, match="is empty"):
        clean_order(make_row(**{column: "   "}))


@pytest.mark.parametrize("column", ["order_purchase_timestamp", "order_estimated_delivery_date"])
def test_clean_empty_required_timestamp_is_rejected(column):
    with pytest.raises(ValueError, match="required but empty"):
        clean_order(make_row(**{column: "   "}))


@pytest.mark.parametrize("column", ["order_purchase_timestamp", "order_approved_at", "order_delivered_carrier_date", "order_delivered_customer_date", "order_estimated_delivery_date"])
def test_clean_unparseable_timestamp_is_rejected(column):
    with pytest.raises(ValueError, match="not a valid timestamp"):
        clean_order(make_row(**{column: "abc"}))


def test_clean_delivered_before_purchase_is_rejected():
    with pytest.raises(ValueError, match="Delivered to customer before purchase"):
        clean_order(make_row(order_purchase_timestamp="2017-10-19 00:00:00"))


def test_clean_order_late_delivery_is_kept():
    clean = clean_order(
        make_row(order_delivered_customer_date="2017-12-25 10:00:00"))
    assert clean["order_delivered_customer_date"] is not None


def test_clean_order_empty_delivery_date_is_kept_as_none():
    clean = clean_order(make_row(order_delivered_customer_date=""))
    assert clean["order_delivered_customer_date"] is None


def test_clean_order_excel_reformatted_timestamp_is_rejected():
    with pytest.raises(ValueError, match="not a valid timestamp"):
        clean_order(make_row(order_purchase_timestamp="10/2/2017 10:56"))


@pytest.mark.parametrize("text, expected", [("2017-10-02 10:56:33", datetime(2017, 10, 2, 13, 56, 33, tzinfo=timezone.utc)),
                                            ("2017-11-18 19:28:06", datetime(2017, 11, 18, 21, 28, 6, tzinfo=timezone.utc))])
def test_parse_olist_time_converts_sao_paulo_to_utc(text, expected):
    assert parse_olist_time(
        text, "order_purchase_timestamp", required=True) == expected


def test_parse_olist_time_empty_optional_returns_none():
    assert parse_olist_time("", "order_approved_at", required=False) is None


def test_parse_olist_time_strips_surrounding_spaces():
    result = parse_olist_time(" 2017-10-02 10:56:33  ",
                              "order_purchase_timestamp", required=True)
    assert result == datetime(2017, 10, 2, 13, 56, 33, tzinfo=timezone.utc)


def test_read_orders_accepts_utf8_bom(tmp_path):
    path = tmp_path / "orders.csv"
    path.write_text(HEADER + GOOD, encoding="utf-8-sig")
    good, rejected, rows_read = read_orders(path=path)
    assert len(good) == 1


HEADER = "order_id,customer_id,order_status,order_purchase_timestamp,order_approved_at,order_delivered_carrier_date,order_delivered_customer_date,order_estimated_delivery_date\n"
GOOD = "a1,c1,delivered,2017-10-02 10:56:33,,,2017-10-10 21:25:13,2017-10-18 00:00:00\n"
ROW_WITH_STATUS_LOST = "a2,c2,lost,2017-10-02 10:56:33,,,2017-10-10 21:25:13,2017-10-18 00:00:00\n"


@pytest.fixture
def write_orders(tmp_path):
    def _write(text: str):
        path = tmp_path / "orders.csv"
        path.write_text(text, encoding="utf-8")
        return path
    return _write


def test_read_orders_valid_file_keeps_all_rows(write_orders):
    path = write_orders(HEADER + GOOD)
    good, rejected, rows_read = read_orders(path=path)
    assert len(good) == 1
    assert good[0]["order_id"] == "a1"
    assert len(rejected) == 0
    assert rows_read == 1


def test_read_orders_duplicate_order_id_is_rejected_with_line(write_orders):
    path = write_orders(HEADER + GOOD + GOOD)
    good, rejected, rows_read = read_orders(path=path)
    assert len(good) == 1
    assert len(rejected) == 1
    assert rejected[0]["reason"] == "Duplicate order_id"
    assert rejected[0]["line"] == 3


def test_read_orders_bad_row_is_rejected_with_line_and_id(write_orders):
    path = write_orders(HEADER + GOOD + ROW_WITH_STATUS_LOST)
    good, rejected, rows_read = read_orders(path=path)
    assert "Unknown order_status" in rejected[0]["reason"]
    assert rejected[0]["line"] == 3
    assert rejected[0]["order_id"] == "a2"


def test_read_orders_missing_column_raises(write_orders):
    path = write_orders("order_id,customer_id\na1,c1\n")
    with pytest.raises(ValueError, match="Missing"):
        read_orders(path=path)


def test_read_orders_missing_file_raises(tmp_path):
    path = tmp_path / "does_not_exist.csv"
    with pytest.raises(FileNotFoundError, match="not found"):
        read_orders(path=path)


def test_check_batch_clean_batch_passes():
    good = [{"order_id": "a1"}, {"order_id": "a2"}]
    check_batch(good=good, rejected=[], rows_read=2)


def test_check_batch_empty_batch_raises():
    with pytest.raises(ValueError, match="Every row was rejected"):
        check_batch(good=[], rejected=[], rows_read=0)


def test_check_batch_duplicate_order_id_raises():
    good = [{"order_id": "a1"}, {"order_id": "a1"}]
    with pytest.raises(ValueError, match="Duplicate order_id"):
        check_batch(good=good, rejected=[], rows_read=2)


def test_check_batch_row_count_mismatch_raises():
    good = [{"order_id": "a1"}, {"order_id": "a2"}]
    with pytest.raises(ValueError, match="Row count mismatch"):
        check_batch(good=good, rejected=[], rows_read=1)


def test_count_oddities_counts_each_case():
    good = [
        clean_order(make_row()),
        clean_order(make_row(order_delivered_customer_date="")),
        clean_order(make_row(order_approved_at="")),
        clean_order(make_row(order_status="canceled")),
        clean_order(
            make_row(order_delivered_carrier_date="2017-10-01 10:56:33"))
    ]
    counts = count_oddities(good)
    assert counts == {
        "delivered_without_delivery_date": 1,
        "delivered_without_approval": 1,
        "canceled_with_delivery_date": 1,
        "carrier_pickup_before_purchase": 1,
    }


def test_read_orders_short_row_is_rejected(write_orders):
    path = write_orders(HEADER + GOOD + "b2,c2,shipped\n")
    good, rejected, rows_read = read_orders(path=path)
    assert len(good) == 1
    assert len(rejected) == 1
    assert rejected[0]["line"] == 3


def test_read_orders_row_with_extra_field_is_rejected(write_orders):
    path = write_orders(HEADER + GOOD.strip() + ",EXTRA\n")
    good, rejected, rows_read = read_orders(path=path)
    assert len(good) == 0
    assert len(rejected) == 1
    assert rejected[0]["line"] == 2


def test_main_failed_run_leaves_no_clean_file(tmp_path, monkeypatch, write_orders):
    import pipeline.clean_orders as c

    # 1. Point the output files to the temp folder, so the test never touches your real data/ and logs/
    monkeypatch.setattr(c, "CLEAN_FILE", tmp_path / "out" / "orders_clean.csv")
    monkeypatch.setattr(c, "REJECT_FILE", tmp_path / "out" / "rejects.csv")
    monkeypatch.setattr(c, "LOG_FILE", tmp_path / "out" / "run.log")

    # 2. Pretend there's a clean file from yesterday's successful run
    c.CLEAN_FILE.parent.mkdir(parents=True)
    c.CLEAN_FILE.write_text("old data from yesterday\n", encoding="utf-8")

    # 3. Today's input: every row is bad, so the gate must fail
    bad = write_orders(
        HEADER + "z9,c9,lost,2017-10-02 10:56:33,,,,2017-10-18 00:00:00\n")

    # 4. main() must end the run as failed...
    with pytest.raises(SystemExit):
        c.main(path=bad)

    # 5. ...and must not leave yesterday's file behind
    assert not c.CLEAN_FILE.exists()

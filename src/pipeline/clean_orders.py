from pathlib import Path
import csv
import logging
from datetime import timezone, datetime
from time import perf_counter
from zoneinfo import ZoneInfo
from collections import Counter


# Step 1:
PROJECT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
OLIST_DIR = RAW_DIR / "olist"
RAW_FILE = OLIST_DIR / "olist_orders_dataset.csv"
PROCESSED_DIR = DATA_DIR / "processed"
CLEAN_FILE = PROCESSED_DIR / "orders_clean.csv"
REJECT_DIR = DATA_DIR / "rejects"
REJECT_FILE = REJECT_DIR / "orders_rejects.csv"
LOG_DIR = PROJECT_DIR / "logs"
LOG_FILE = LOG_DIR / "clean_orders.log"
REQUIRED_COLUMNS = {"order_id", "customer_id", "order_status", "order_purchase_timestamp", "order_approved_at",
                    "order_delivered_carrier_date", "order_delivered_customer_date", "order_estimated_delivery_date"}
OUTPUT_COLUMNS = ["order_id", "customer_id", "order_status", "order_purchase_timestamp", "order_approved_at",
                  "order_delivered_carrier_date", "order_delivered_customer_date", "order_estimated_delivery_date"]
REJECT_COLUMNS = ["line", "order_id", "reason"]
KNOWN_STATUSES = {"delivered", "shipped", "canceled", "created",
                  "approved", "invoiced", "processing", "unavailable"}
logger = logging.getLogger(__name__)


def read_orders(path: Path) -> tuple:
    try:
        with path.open(mode="r", newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
            if missing:
                raise ValueError(f"Missing the columns: {sorted(missing)}")
            count = 0
            good = []
            rejected = []
            seen_ids = set()
            for line, row in enumerate(reader, start=2):
                count += 1
                # Too few values: DictReader fills the missing ones with None.
                # Too many values: DictReader stores the extras under the key None.
                if None in row or None in row.values():
                    rejected.append({
                        "line": line,
                        "order_id": row.get("order_id") or "",
                        "reason": "Wrong number of fields",
                    })
                    continue
                try:
                    clean = clean_order(row)
                except ValueError as e:
                    rejected.append({
                        "line": line,
                        "order_id": row["order_id"],
                        "reason": str(e),
                    })
                else:
                    if clean["order_id"] in seen_ids:
                        rejected.append({
                            "line": line,
                            "order_id": clean["order_id"],
                            "reason": "Duplicate order_id"
                        })
                    else:
                        seen_ids.add(clean["order_id"])
                        good.append({
                            "order_id": clean["order_id"],
                            "customer_id": clean["customer_id"],
                            "order_status": clean["order_status"],
                            "order_purchase_timestamp": clean["order_purchase_timestamp"],
                            "order_approved_at": clean["order_approved_at"],
                            "order_delivered_carrier_date": clean["order_delivered_carrier_date"],
                            "order_delivered_customer_date": clean["order_delivered_customer_date"],
                            "order_estimated_delivery_date": clean["order_estimated_delivery_date"],
                        })
            return good, rejected, count
    except FileNotFoundError as e:
        raise FileNotFoundError(f"Orders file not found: {path}") from e


def main(path: Path):
    REJECT_FILE.parent.mkdir(parents=True, exist_ok=True)
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
                        encoding="utf-8", level=logging.INFO, filename=LOG_FILE)
    try:
        CLEAN_FILE.unlink(missing_ok=True)
        started = perf_counter()
        good, rejected, rows_read = read_orders(path=path)
        logger.info("rows read: %d", rows_read)
        logger.info("rows kept: %d", len(good))
        if rejected:
            logger.warning("rows rejected: %d", len(rejected))
        write_csv(REJECT_FILE, rejected, REJECT_COLUMNS)
        check_batch(good=good, rejected=rejected, rows_read=rows_read)
        write_csv(CLEAN_FILE, good, OUTPUT_COLUMNS)
        count = count_oddities(good=good)
        for key, value in count.items():
            if value > 0:
                logger.warning("%s: %d", key, value)
        duration_ms = (perf_counter() - started) * 1000
        logger.info("duration_ms= %.0f", duration_ms)
    except (FileNotFoundError, ValueError):
        logger.exception("clean_orders failed")
        raise SystemExit(1)
    except Exception:
        logger.exception("clean_orders failed")
        raise SystemExit(1)
    finally:
        logger.info("Done with: %s", path.name)

# Step 2:


def parse_olist_time(value: str, column: str, *, required: bool) -> datetime | None:
    if value.strip() == "":
        if required:
            raise ValueError(f"{column} is required but empty")
        else:
            return None
    try:
        value_label = datetime.strptime(
            value.strip(), "%Y-%m-%d %H:%M:%S").replace(tzinfo=ZoneInfo("America/Sao_Paulo"))
        value_convert = value_label.astimezone(tz=timezone.utc)
        return value_convert
    except ValueError as e:
        raise ValueError(
            f"{column} is not a valid timestamp: {value!r}") from e


def clean_order(row: dict) -> dict:
    order_id = row["order_id"].strip()
    if order_id == "":
        raise ValueError("order_id is empty")
    customer_id = row["customer_id"].strip()
    if customer_id == "":
        raise ValueError("customer_id is empty")
    order_status = row["order_status"].strip().lower()
    if order_status not in KNOWN_STATUSES:
        raise ValueError(f"Unknown order_status: {order_status}")
    order_purchase_timestamp = parse_olist_time(
        row["order_purchase_timestamp"], column="order_purchase_timestamp", required=True)
    order_approved_at = parse_olist_time(
        row["order_approved_at"], column="order_approved_at", required=False
    )
    order_delivered_carrier_date = parse_olist_time(
        row["order_delivered_carrier_date"], column="order_delivered_carrier_date", required=False)
    order_delivered_customer_date = parse_olist_time(
        row["order_delivered_customer_date"], column="order_delivered_customer_date", required=False
    )
    order_estimated_delivery_date = parse_olist_time(
        row["order_estimated_delivery_date"], column="order_estimated_delivery_date", required=True
    )
    if order_delivered_customer_date is not None and order_delivered_customer_date < order_purchase_timestamp:
        raise ValueError("Delivered to customer before purchase")
    return {
        "order_id": order_id,
        "customer_id": customer_id,
        "order_status": order_status,
        "order_purchase_timestamp": order_purchase_timestamp,
        "order_approved_at": order_approved_at,
        "order_delivered_carrier_date": order_delivered_carrier_date,
        "order_delivered_customer_date": order_delivered_customer_date,
        "order_estimated_delivery_date": order_estimated_delivery_date,
    }


def write_csv(path: Path, rows: list, fieldnames: list):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open(mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            out = {}
            for key, value in row.items():
                if isinstance(value, datetime):
                    out[key] = value.isoformat()
                else:
                    out[key] = value
            writer.writerow(out)


def count_oddities(good: list) -> dict:
    counts = {
        "delivered_without_delivery_date": 0,
        "delivered_without_approval": 0,
        "canceled_with_delivery_date": 0,
        "carrier_pickup_before_purchase": 0,
    }
    for row in good:
        if row["order_status"] == "delivered" and row["order_delivered_customer_date"] is None:
            counts["delivered_without_delivery_date"] += 1
        if row["order_status"] == "delivered" and row["order_approved_at"] is None:
            counts["delivered_without_approval"] += 1
        if row["order_status"] == "canceled" and row["order_delivered_customer_date"] is not None:
            counts["canceled_with_delivery_date"] += 1
        if row["order_delivered_carrier_date"] is not None and row["order_delivered_carrier_date"] < row["order_purchase_timestamp"]:
            counts["carrier_pickup_before_purchase"] += 1
    return counts


def check_batch(good: list, rejected: list, rows_read: int) -> None:
    if len(good) + len(rejected) != rows_read:
        raise ValueError(
            f"Row count mismatch: read {rows_read}, kept {len(good)}, rejected {len(rejected)}")
    if len(good) == 0:
        raise ValueError(
            "No valid order: Every row was rejected"
        )
    ids = [row["order_id"] for row in good]
    if len(ids) != len(set(ids)):
        counts = Counter(ids)
        duplicates = sorted(order_id for order_id,
                            n in counts.items() if n > 1)
        raise ValueError(f"Duplicate order_id: {duplicates}")


if __name__ == "__main__":
    main(path=RAW_FILE)

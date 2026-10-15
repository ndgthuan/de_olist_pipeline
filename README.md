# de_olist_pipeline

A batch data pipeline built on the [Olist Brazilian e-commerce dataset](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce).
It extracts CSVs and daily FX rates, loads them into PostgreSQL, models them with dbt and runs on a schedule.

> Status: Phase 0 (project setup). Pipeline code arrives week by week.

## How to set up

Requires Python 3.12+ and Git. Commands are for Windows PowerShell.

1. **Clone the repo**
   ```powershell
   git clone https://github.com/ndgthuan/de_olist_pipeline.git
   cd de_olist_pipeline
   ```
2. **Create and activate a virtual environment**
   ```powershell
   py -3.13 -m venv .venv
   .venv\Scripts\Activate.ps1
   ```
3. **Install the project with dev tools** (editable, so code changes apply without reinstalling)
   ```powershell
   python -m pip install -e ".[dev]"
   ```
4. **Download the data.** Get the dataset from Kaggle (free account) and unzip the 9 CSVs into `data/raw/olist/`.
   The `data/` folder is git-ignored.
5. **Copy the env file**
   ```powershell
   Copy-Item .env.example .env
   ```
6. **Run the tests**
   ```powershell
   python -m pytest
   ```

## Project layout

```text
src/pipeline/   pipeline code (extract, transform, load, config)
tests/          pytest tests and tiny fixture files
data/raw/olist/ downloaded CSVs (not in git)
```

## The data: what one row means

Checked by counting duplicate keys in each file.

| Table | One row is... | Unique key |
|---|---|---|
| `orders` | one order (99,441 rows) | `order_id` |
| `order_items` | one item line inside an order. An order with 3 items has 3 rows | `order_id` + `order_item_id` |
| `order_payments` | one payment for an order. An order paid with a voucher and a card has 2 rows | `order_id` + `payment_sequential` |
| `order_reviews` | one review of one order. A few `review_id`s cover several orders | `review_id` + `order_id` |
| `customers` | one customer *per order*. The same person gets a new `customer_id` each order; `customer_unique_id` is the real person | `customer_id` |
| `sellers` | one seller | `seller_id` |
| `products` | one product | `product_id` |
| `geolocation` | one lat/lng point. A zip prefix has many points, so dedupe before joining | none |
| `product_category_name_translation` | one Portuguese category and its English name | `product_category_name` |

Joining `orders` to `order_items` gives one row per item, not per order. Sum item prices before comparing with order-level totals.

## Cleaning rules: olist_orders

Rules for `olist_orders_dataset.csv` (99,441 rows), decided after profiling the file. The counts are from the downloaded dataset.

Principle: reject data that is broken, not data that is bad news. A late delivery is a real fact about the business and stays in.

### Converted

| Column | Rule | Why |
|---|---|---|
| All 5 timestamp columns | Parse `YYYY-MM-DD HH:MM:SS`, label as `America/Sao_Paulo`, convert to UTC | The source has no time zone. Olist is a Brazilian company, so the values are São Paulo local time. A zone name is used, not a fixed `-03:00`, because Brazil had summer time in 2016–2018 |
| `order_status` | Trim spaces, lowercase | So the same status is always written the same way |

### Kept, with a warning in the log

These rows look odd but are not provably wrong, so the order stays and the run logs how many there are.

| Case | Today | Decision | Why |
|---|---|---|---|
| `delivered` with no `order_delivered_customer_date` | 8 | Keep, date stays empty | The order and its revenue are real. Delivery-time metrics skip rows with no delivery date |
| `delivered` with no `order_approved_at` | 14 | Keep, date stays empty | Same reason, and the approval time is not used for the main metrics |
| `canceled` that has a delivery date | 6 | Keep | It can be a real case (delivered, then canceled and refunded) and cannot be checked from this file |
| Carrier pickup before purchase | 166 | Keep | The pickup time likely comes from another system's clock and is not used for the main metrics |

An empty timestamp is normal for orders that have not reached that step yet (for example `shipped` has no delivery date). Empty stays empty; it is never replaced with a made-up date.

### Rejected

A rejected row is not written to the clean file. It goes to the reject file with the reason.

| Case | Today |
|---|---|
| Empty `order_id` or `customer_id` | 0 |
| Empty `order_purchase_timestamp` or `order_estimated_delivery_date` | 0 |
| A timestamp that cannot be parsed | 0 |
| `order_status` is not one of the 8 known values: `created`, `approved`, `invoiced`, `processing`, `shipped`, `delivered`, `canceled`, `unavailable` | 0 |
| Delivered to the customer before the purchase time | 0 |
| Duplicate `order_id`: the first row is kept, later ones are rejected | 0 |

Known limit of the duplicate rule: the first row in the file is not always the correct one. A later version may keep the most recent row instead.

Reject file columns: `line` (line number in the source CSV), `order_id`, `reason`.

### Checks on every run

- rows read = rows kept + rows rejected
- `order_id` is unique in the clean file
- the clean file is not empty

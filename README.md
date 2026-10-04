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

"""
JSON + CSV demo: read, query, and summarize structured data files.

Two data files are planted at /tmp/nori_data_demo:
  - products.json  — a catalog of 8 products with price, category, and stock
  - orders.csv     — 12 sales orders with product_id, quantity, and total

The agent is asked to read both files, answer specific questions about the data,
and produce a brief combined summary.
"""

import asyncio
import json
import os
import shutil
import textwrap

import config
from nori import Agent
from nori.audit import AuditLogger
from nori.tools.csv_read import CsvRead
from nori.tools.file_write import FileWrite
from nori.tools.json_read import JsonRead


WORKDIR = "/tmp/nori_data_demo"

PRODUCTS = [
    {"id": "P001", "name": "Widget A", "category": "widgets", "price": 9.99,  "stock": 120},
    {"id": "P002", "name": "Widget B", "category": "widgets", "price": 14.99, "stock": 45},
    {"id": "P003", "name": "Gadget X", "category": "gadgets", "price": 49.99, "stock": 30},
    {"id": "P004", "name": "Gadget Y", "category": "gadgets", "price": 79.99, "stock": 8},
    {"id": "P005", "name": "Doohickey", "category": "misc",    "price": 4.99,  "stock": 200},
    {"id": "P006", "name": "Thingamajig", "category": "misc",  "price": 24.99, "stock": 0},
    {"id": "P007", "name": "Sprocket",   "category": "widgets","price": 19.99, "stock": 60},
    {"id": "P008", "name": "Flux Cap",   "category": "gadgets","price": 299.99,"stock": 3},
]

ORDERS_CSV = textwrap.dedent("""\
    order_id,product_id,quantity,unit_price,total
    O001,P001,5,9.99,49.95
    O002,P003,2,49.99,99.98
    O003,P005,10,4.99,49.90
    O004,P002,3,14.99,44.97
    O005,P008,1,299.99,299.99
    O006,P001,8,9.99,79.92
    O007,P004,1,79.99,79.99
    O008,P007,4,19.99,79.96
    O009,P003,1,49.99,49.99
    O010,P005,20,4.99,99.80
    O011,P002,2,14.99,29.98
    O012,P006,0,24.99,0.00
""")

SYSTEM_PROMPT = """\
You are a data analyst. Read structured data files carefully, then answer
questions precisely using the data. Do the math yourself when needed.
"""

TASK = f"""\
Two data files are in {WORKDIR}:
  - products.json
  - orders.csv

Answer each question below using JsonRead and CsvRead:

1. How many products are out of stock (stock = 0)?
2. What is the most expensive product? What category is it in?
3. What is the total revenue across all orders (sum of the "total" column)?
4. Which product_id appears most often in orders?
5. Which category has the most products?

After answering all five questions, write a two-sentence executive summary to
{WORKDIR}/summary.txt using FileWrite.
"""


def setup() -> None:
    shutil.rmtree(WORKDIR, ignore_errors=True)
    os.makedirs(WORKDIR)
    with open(f"{WORKDIR}/products.json", "w") as f:
        json.dump(PRODUCTS, f, indent=2)
    with open(f"{WORKDIR}/orders.csv", "w") as f:
        f.write(ORDERS_CSV)


def cleanup() -> None:
    shutil.rmtree(WORKDIR, ignore_errors=True)


async def main() -> None:
    setup()

    agent = Agent(
        name="DataAnalyst",
        system_prompt=SYSTEM_PROMPT,
        tools=[JsonRead, CsvRead, FileWrite],
        max_turns=20,
    )
    agent.narration = True
    agent.auditor = AuditLogger("logs/json_csv_demo.audit.log")

    print("=" * 60)
    print("Nori JSON + CSV demo")
    print("=" * 60)
    print()

    try:
        result = await agent.run(TASK)
        print(f"\nAgent: {result}")
    finally:
        cleanup()
        agent.auditor.close()

    print(f"\nTurns: {agent.turn_count}  |  Cost: ${agent.cost:.4f}")


asyncio.run(main())

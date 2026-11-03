"""
init_db.py - Initializes the SQLite inventory database for v2.
Seeds 8 realistic building materials / flooring trade-desk SKUs with
historical demand parameters, supplier lead times, and pack constraints.
"""

import sqlite3


def init_database():
    conn = sqlite3.connect("inventory.db")
    cursor = conn.cursor()

    # Create SKU Master Table
    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS inventory_catalog (
        sku TEXT PRIMARY KEY,
        description TEXT NOT NULL,
        vendor TEXT NOT NULL,
        category TEXT NOT NULL,
        on_hand INTEGER NOT NULL,
        unit_cost REAL NOT NULL,
        unit_price REAL NOT NULL,
        pack_size INTEGER NOT NULL,
        daily_mean REAL NOT NULL,
        daily_sd REAL NOT NULL,
        lead_mean REAL NOT NULL,
        lead_sd REAL NOT NULL
    )
    """
    )

    # 8 realistic commercial trade-desk SKUs
    skus = [
        (
            "TILE-001",
            "12x24 Carrara Matte Porcelain",
            "Dal-Tile Corp",
            "Tile",
            620,
            22.50,
            38.99,
            48,
            45.0,
            12.0,
            18.0,
            2.5,
        ),
        (
            "TILE-002",
            "6x36 Aspen Gray Wood Plank Tile",
            "Mohawk Ind",
            "Tile",
            180,
            28.00,
            46.50,
            40,
            25.0,
            8.0,
            14.0,
            3.0,
        ),
        (
            "MORT-101",
            "Large Format Polymer White Mortar 50lb",
            "Custom Building",
            "Mortar",
            96,
            16.20,
            26.98,
            48,
            30.0,
            7.0,
            7.0,
            1.5,
        ),
        (
            "MORT-102",
            "Multi-Surface Floor Gray Mortar 50lb",
            "Custom Building",
            "Mortar",
            410,
            11.40,
            18.50,
            48,
            35.0,
            6.0,
            7.0,
            1.0,
        ),
        (
            "VINYL-201",
            "7in Luxury Vinyl Plank Waterproof",
            "Shaw Industries",
            "Vinyl",
            310,
            32.00,
            54.00,
            36,
            22.0,
            9.0,
            21.0,
            4.0,
        ),
        (
            "GROUT-301",
            "Pre-Mixed Stainproof Grout Pewter 1gal",
            "Custom Building",
            "Grout",
            42,
            38.50,
            59.98,
            12,
            8.0,
            3.0,
            10.0,
            2.0,
        ),
        (
            "UNDR-401",
            "Sound Reduction Foam Underlayment 100sqft",
            "QEP Co",
            "Underlayment",
            120,
            24.00,
            42.00,
            20,
            15.0,
            5.0,
            12.0,
            2.0,
        ),
        (
            "TOOL-501",
            "Stainless Steel 1/2in Square Notch Trowel",
            "Marshalltown",
            "Tools",
            18,
            14.00,
            24.97,
            6,
            4.0,
            2.0,
            15.0,
            3.0,
        ),
    ]

    cursor.executemany(
        """
    INSERT OR REPLACE INTO inventory_catalog VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
        skus,
    )

    conn.commit()
    conn.close()
    print("✅ inventory.db successfully created and seeded with 8 SKUs!")


if __name__ == "__main__":
    init_database()
from sqlalchemy import Date, text


def quote_ident(identifier):
    return f'"{identifier}"'


def delete_legacy_duplicates(conn, table_name, unique_cols):
    partition = ", ".join(quote_ident(col) for col in unique_cols)
    conn.execute(
        text(
            f"""
            DELETE FROM {quote_ident(table_name)}
            WHERE ctid IN (
                SELECT ctid
                FROM (
                    SELECT ctid,
                           ROW_NUMBER() OVER (
                               PARTITION BY {partition}
                               ORDER BY ctid DESC
                           ) AS rn
                    FROM {quote_ident(table_name)}
                ) dedup
                WHERE dedup.rn > 1
            )
            """
        )
    )


def create_unique_index(conn, table_name, unique_cols):
    index_name = f"{table_name}_{'_'.join(unique_cols)}_uidx"
    cols = ", ".join(quote_ident(col) for col in unique_cols)
    conn.execute(
        text(
            f"""
            CREATE UNIQUE INDEX IF NOT EXISTS {quote_ident(index_name)}
            ON {quote_ident(table_name)} ({cols})
            """
        )
    )


def upsert_dataframe(conn, df, table_name, unique_cols, date_cols=None):
    if df is None or df.empty:
        return

    working = df.copy()
    date_cols = date_cols or []
    for col in date_cols:
        if col in working.columns:
            working[col] = working[col].astype("string")

    staging_table = f"{table_name}_staging"
    conn.execute(
        text(
            f"""
            CREATE TEMP TABLE {quote_ident(staging_table)}
            (LIKE {quote_ident(table_name)} INCLUDING DEFAULTS)
            ON COMMIT DROP
            """
        )
    )

    dtype = {col: Date() for col in date_cols if col in working.columns}
    working.to_sql(
        staging_table,
        conn,
        if_exists="append",
        index=False,
        dtype=dtype,
    )

    columns = list(working.columns)
    cols_csv = ", ".join(quote_ident(col) for col in columns)
    update_cols = [col for col in columns if col not in unique_cols]
    update_set = ",\n                    ".join(
        f"{quote_ident(col)} = EXCLUDED.{quote_ident(col)}" for col in update_cols
    )
    conflict_cols = ", ".join(quote_ident(col) for col in unique_cols)

    conn.execute(
        text(
            f"""
            INSERT INTO {quote_ident(table_name)} ({cols_csv})
            SELECT {cols_csv}
            FROM {quote_ident(staging_table)}
            ON CONFLICT ({conflict_cols})
            DO UPDATE SET
                    {update_set}
            """
        )
    )

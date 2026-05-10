import sqlite3
import queue
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "orders.db")
POOL_SIZE = 5


class ConnectionPool:
    def __init__(self, db_path, size=POOL_SIZE):
        self._pool = queue.Queue(maxsize=size)
        for _ in range(size):
            conn = sqlite3.connect(db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            self._pool.put(conn)

    def acquire(self, timeout=2.0):
        try:
            return self._pool.get(timeout=timeout)
        except queue.Empty:
            raise RuntimeError("Connection pool exhausted — too many concurrent requests")

    def release(self, conn):
        self._pool.put(conn)


_pool: ConnectionPool | None = None


def init_pool(db_path=DB_PATH, size=POOL_SIZE):
    global _pool
    _pool = ConnectionPool(db_path, size)


def get_pool():
    global _pool
    if _pool is None:
        init_pool()
    return _pool


def execute_query(sql: str, params=()) -> list:
    pool = get_pool()
    conn = pool.acquire()
    try:
        cursor = conn.execute(sql, params)
        results = cursor.fetchall()
        return [dict(row) for row in results]
    finally:
        pool.release(conn)


def execute_write(sql: str, params=()) -> int:
    pool = get_pool()
    conn = pool.acquire()
    try:
        cursor = conn.execute(sql, params)
        conn.commit()
        row_id = cursor.lastrowid
        return row_id
    finally:
        pool.release(conn)

import os
import unittest
from unittest.mock import patch


os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://usuario:clave@localhost:5432/mc10_cloud_test",
)

import main


class FakeCursor:
    def __init__(self) -> None:
        self.executed = []

    def execute(self, query, params=None):
        self.executed.append((query, params))
        return self

    def executemany(self, query, params):
        self.executed.append((query, params))
        return self


class FakeConnection:
    def __init__(self) -> None:
        self.executed = []
        self.cursor_instance = FakeCursor()
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def execute(self, query, params=None):
        self.executed.append((query, params))
        return self.cursor_instance

    def cursor(self):
        return self.cursor_instance

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


class DatabaseAdapterTests(unittest.TestCase):
    def test_qmark_placeholders_are_converted(self):
        query = "SELECT * FROM sales WHERE sale_id = ? AND machine_serial = ?"
        self.assertEqual(
            main.DatabaseConnection._postgres_query(query),
            "SELECT * FROM sales WHERE sale_id = %s AND machine_serial = %s",
        )

    def test_successful_context_commits_and_closes(self):
        fake = FakeConnection()
        with patch.object(main.psycopg, "connect", return_value=fake):
            with main.get_db() as connection:
                connection.execute("SELECT * FROM machines WHERE serial = ?", ("1",))

        self.assertEqual(
            fake.executed[0],
            ("SELECT * FROM machines WHERE serial = %s", ("1",)),
        )
        self.assertTrue(fake.committed)
        self.assertFalse(fake.rolled_back)
        self.assertTrue(fake.closed)

    def test_failed_context_rolls_back_and_closes(self):
        fake = FakeConnection()
        with self.assertRaises(RuntimeError):
            with patch.object(main.psycopg, "connect", return_value=fake):
                with main.get_db():
                    raise RuntimeError("prueba")

        self.assertFalse(fake.committed)
        self.assertTrue(fake.rolled_back)
        self.assertTrue(fake.closed)


if __name__ == "__main__":
    unittest.main()

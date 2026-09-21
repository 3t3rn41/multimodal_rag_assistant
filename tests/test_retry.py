import unittest

from ingestion.retry import RetryPolicy, retry_call


class RetryTests(unittest.TestCase):
    def test_retries_transient_operation_with_exponential_backoff(self) -> None:
        attempts = 0
        waits: list[float] = []

        def operation() -> str:
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise RuntimeError("temporary failure")
            return "ok"

        result = retry_call(
            operation,
            policy=RetryPolicy(max_retries=3, backoff_seconds=0.25),
            is_retryable=lambda exc: isinstance(exc, RuntimeError),
            sleeper=waits.append,
        )

        self.assertEqual(result, "ok")
        self.assertEqual(attempts, 3)
        self.assertEqual(waits, [0.25, 0.5])

    def test_does_not_retry_non_transient_error(self) -> None:
        attempts = 0

        def operation() -> None:
            nonlocal attempts
            attempts += 1
            raise ValueError("bad request")

        with self.assertRaises(ValueError):
            retry_call(
                operation,
                policy=RetryPolicy(max_retries=3, backoff_seconds=0.01),
                is_retryable=lambda exc: isinstance(exc, RuntimeError),
                sleeper=lambda _: self.fail("unexpected retry"),
            )
        self.assertEqual(attempts, 1)


if __name__ == "__main__":
    unittest.main()

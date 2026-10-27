"""
Latency Measurement Script
Compares response time: through API Gateway vs direct service call.
"""
import sys
import httpx
import time
import statistics
import asyncio

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

GATEWAY_URL = "http://localhost:8000"
USER_SERVICE_DIRECT = "http://localhost:8001"
ORDER_SERVICE_DIRECT = "http://localhost:8002"
NUM_REQUESTS = 20  # number of test requests

async def measure_latency(client: httpx.AsyncClient, url: str, headers: dict = None, label: str = "") -> list[float]:
    latencies = []
    for i in range(NUM_REQUESTS):
        start = time.perf_counter()
        try:
            resp = await client.get(url, headers=headers or {})
            elapsed = (time.perf_counter() - start) * 1000  # ms
            latencies.append(elapsed)
        except Exception as e:
            print(f"   Request {i+1} failed: {e}")
    return latencies

def print_stats(label: str, latencies: list[float]):
    if not latencies:
        print(f"{label}: No data")
        return
    print(f"\n {label}")
    print(f"   Requests:  {len(latencies)}")
    print(f"   Min:       {min(latencies):.2f} ms")
    print(f"   Max:       {max(latencies):.2f} ms")
    print(f"   Mean:      {statistics.mean(latencies):.2f} ms")
    print(f"   Median:    {statistics.median(latencies):.2f} ms")
    print(f"   Stdev:     {statistics.stdev(latencies):.2f} ms" if len(latencies) > 1 else "")

async def main():
    print("=" * 55)
    print("   Latency Measurement: Gateway vs Direct")
    print("=" * 55)

    # Step 1: Get JWT token
    async with httpx.AsyncClient() as client:
        print("\n Getting JWT token...")
        resp = await client.post(f"{GATEWAY_URL}/auth/login", json={"username": "testuser", "password": "secret"})
        if resp.status_code != 200:
            print(f" Failed to get token: {resp.text}")
            return
        token = resp.json()["access_token"]
        auth_headers = {"Authorization": f"Bearer {token}"}
        print("    Token obtained")

    # Step 2: Warm up
    print("\n Warming up (5 requests)...")
    async with httpx.AsyncClient() as client:
        for _ in range(5):
            await client.get(f"{GATEWAY_URL}/users", headers=auth_headers)
            await client.get(f"{USER_SERVICE_DIRECT}/users")

    # Step 3: Measure latency
    print(f"\n  Running {NUM_REQUESTS} requests each...\n")

    async with httpx.AsyncClient(timeout=10.0) as client:
        # Through gateway (JWT + rate limit overhead)
        print("   Measuring through API Gateway...")
        gateway_latencies = await measure_latency(
            client, f"{GATEWAY_URL}/users",
            headers=auth_headers,
            label="Gateway /users"
        )

        await asyncio.sleep(1)  # avoid rate limit

        # Direct to service (no gateway)
        print("   Measuring direct to User Service...")
        direct_latencies = await measure_latency(
            client, f"{USER_SERVICE_DIRECT}/users",
            label="Direct /users"
        )

    # Step 4: Print results
    print_stats("Via API Gateway → User Service", gateway_latencies)
    print_stats("Direct → User Service (no gateway)", direct_latencies)

    if gateway_latencies and direct_latencies:
        gateway_mean = statistics.mean(gateway_latencies)
        direct_mean = statistics.mean(direct_latencies)
        overhead = gateway_mean - direct_mean
        print(f"\n{'=' * 55}")
        print(f"   Gateway overhead: {overhead:+.2f} ms per request")
        print(f"     ({(overhead/direct_mean*100):.1f}% slower than direct)")
        print(f"{'=' * 55}")
        print("\n Overhead includes: JWT verification + rate limit check + HTTP proxy hop")

if __name__ == "__main__":
    asyncio.run(main())

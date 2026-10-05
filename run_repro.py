"""Reproduce OpenZeppelin Relayer issue #808 (gas_price_cap leaves a tx stuck after a spike).

Sequence (anvil in --no-mining mode so we control base fee and inclusion):
  1. baseline: base fee low, send one tx via the relayer API with speed fast
  2. spike: set next block base fee well above gas_price_cap and mine; the tx is now underpriced
  3. let the relayer try to bump; it is capped, so it logs "bumped gas price does not meet minimum requirement"
  4. evict: anvil_dropTransaction for every hash the relayer knows (simulates mempool eviction)
  5. recovery: base fee back to low, keep mining blocks; watch whether the relayer resubmits and the tx mines
Logs to logs/run.log; final verdict printed.
"""
import json, sys, time
import httpx

RELAYER = "http://127.0.0.1:18081"
KEY = "repro808-api-key-0123456789abcdef"
ANVIL = "http://127.0.0.1:18545"
RID = "anvil-capped"
CAP = 800_000_000           # wei, matches config.json
LOW_BASE = 100_000_000      # 0.1 gwei
SPIKE_BASE = 5_000_000_000  # 5 gwei
TO = "0x70997970C51812dc3A010C7d01b50e0d17dc79C8"  # anvil account #1
LOG = open(__file__.rsplit("/", 1)[0] + "/logs/run.log", "a")

def log(msg):
    line = f"{time.strftime('%H:%M:%S')} {msg}"
    print(line, flush=True); LOG.write(line + "\n"); LOG.flush()

def rpc(method, params=None):
    r = httpx.post(ANVIL, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or []}, timeout=20)
    j = r.json()
    if "error" in j:
        raise RuntimeError(f"{method}: {j['error']}")
    return j["result"]

def api(method, path, body=None):
    r = httpx.request(method, RELAYER + path, headers={"Authorization": f"Bearer {KEY}"}, json=body, timeout=30)
    return r.status_code, r.json()

def base_fee():
    return int(rpc("eth_getBlockByNumber", ["latest", False])["baseFeePerGas"], 16)

def mine(n=1, base=None):
    for _ in range(n):
        if base is not None:
            rpc("anvil_setNextBlockBaseFeePerGas", [hex(base)])
        rpc("evm_mine")

def tx_state(tx_id):
    code, j = api("GET", f"/api/v1/relayers/{RID}/transactions/{tx_id}")
    d = j.get("data", {})
    return d.get("status"), d.get("hash"), d.get("hashes") or [], d.get("max_fee_per_gas"), d.get("max_priority_fee_per_gas"), d.get("status_reason")

def pending_in_anvil():
    pool = rpc("txpool_content")
    pend = pool.get("pending", {}); queued = pool.get("queued", {})
    return sum(len(v) for v in pend.values()), sum(len(v) for v in queued.values())

def main():
    log("=== repro #808 start; Relayer image openzeppelin/openzeppelin-relayer:v1.8.0, anvil no-mining")
    mine(2, LOW_BASE)
    log(f"baseline base fee {base_fee()} wei, cap {CAP} wei")
    code, j = api("POST", f"/api/v1/relayers/{RID}/transactions", {"to": TO, "value": 1, "data": "0x", "speed": "fast", "gas_limit": 21000})
    log(f"submit -> {code} {json.dumps(j)[:300]}")
    tx_id = j["data"]["id"]
    # wait until relayer has broadcast (status Submitted with hash)
    for _ in range(30):
        st = tx_state(tx_id); log(f"state {st}")
        if st[1]: break
        time.sleep(3)
    log(f"anvil pool pending/queued: {pending_in_anvil()}")
    # 2. spike: price way above cap, mine blocks so the relayer sees it
    log("--- spike: base fee 5 gwei for 90 s")
    t0 = time.time()
    while time.time() - t0 < 90:
        mine(1, SPIKE_BASE); time.sleep(6)
        st = tx_state(tx_id); log(f"spike state {st}; pool {pending_in_anvil()}")
    # 3. evict every known hash (mempool eviction)
    st = tx_state(tx_id)
    hashes = set(st[2]) | ({st[1]} if st[1] else set())
    for h in hashes:
        try:
            ok = rpc("anvil_dropTransaction", [h]); log(f"dropTransaction {h} -> {ok}")
        except Exception as e:
            log(f"dropTransaction {h} failed: {e}")
    log(f"after eviction pool {pending_in_anvil()}")
    # 4. recovery: base fee low again, keep mining
    log("--- recovery: base fee 0.1 gwei, mining every 5 s for up to 20 min")
    t0 = time.time(); verdict = "STUCK (not mined within 20 min after recovery)"
    while time.time() - t0 < 1200:
        mine(1, LOW_BASE); time.sleep(5)
        st = tx_state(tx_id)
        if int((time.time() - t0)) % 30 < 5:
            log(f"recovery state {st}; pool {pending_in_anvil()}; base fee {base_fee()}")
        if st[0] in ("mined", "confirmed"):
            verdict = f"RECOVERED: status {st[0]} hash {st[1]} after {int(time.time()-t0)} s"; break
        if st[0] in ("failed", "expired", "canceled"):
            verdict = f"TERMINAL: status {st[0]} reason {st[5]}"; break
    log(f"=== VERDICT: {verdict}")
    log(f"final state {tx_state(tx_id)}")

if __name__ == "__main__":
    main()

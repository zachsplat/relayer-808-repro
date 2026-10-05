# Reproduction of OpenZeppelin Relayer issue #808 on v1.8.0

`gas_price_cap` leaves a transaction stuck after a gas spike: https://github.com/OpenZeppelin/openzeppelin-relayer/issues/808

This is the setup behind my comment on that issue. It runs the unmodified `openzeppelin/openzeppelin-relayer:v1.8.0` image against anvil in no-mining mode, so the test controls the base fee and block production, and drives the whole scenario with one Python script.

## What it shows

1. With base fee at 0.1 gwei and `gas_price_cap` at 0.8 gwei, a `speed: fast` transfer is priced at the cap on the first attempt and reaches `submitted`.
2. Base fee is raised to 5 gwei. Anvil evicts the underpriced transaction on the next block (pool empty, sender nonce unchanged). The relayer keeps logging `transaction not yet mined`.
3. Base fee returns to 0.1 gwei and blocks are mined every 5 seconds for 20 minutes. The relayer logs this pair every 12 seconds and never broadcasts again:

```
transaction has been pending for too long, resubmitting
bumped gas price does not meet minimum requirement, skipping resubmission
```

In my run: 99 skip warnings, one `send_raw_transaction` in the whole run (the original), status `submitted` throughout, nothing mined with the base fee at one eighth of the cap. Full driver output is in `logs/run.log` and the relevant relayer lines in `logs/relayer-excerpt.log`.

## Why, as far as I can tell from the 1.8.0 source

- `src/domain/transaction/evm/price_calculator.rs`, `handle_eip1559_bump`: the minimum bump is 1.1x the previous `max_fee_per_gas` and `max_priority_fee_per_gas`; both new values are then capped at `gas_price_cap`; `is_min_bumped` is true only if the capped values still meet the minimum. Once the previous fees equal the cap, they never do.
- `src/domain/transaction/evm/evm_transaction.rs`, `resubmit_transaction`: when `is_min_bumped` is false it logs the warning and returns without broadcasting. No path re-sends the already-signed payload unchanged.

Two differences from the original report: anvil drops an underpriced transaction on the next block rather than under mempool pressure, and the first submission here hits the cap immediately instead of after several bumps. The end state is the same. I have not tried cancel or replace through the API.

## Run it

Requirements: Docker with Compose, Python 3.10+, `pip install httpx eth-account`.

```bash
python3 generate_keystore.py          # keystore for anvil's public dev account #0
touch logs/receiver.log               # bind-mounted into the receiver; must exist as a file
docker compose -p repro808 up -d      # anvil, redis, a webhook receiver, relayer 1.8.0
# wait ~15 s for "all health checks passed" in: docker logs repro808-relayer
python3 run_repro.py                  # about 23 minutes; prints a VERDICT line at the end
docker compose -p repro808 down -v
```

Ports used on localhost: 18545 (anvil), 18081 (relayer API). The relayer API key and webhook signing key in `docker-compose.yml` are throwaway values for this test.

## Files

- `docker-compose.yml`: anvil 1.8.1 (`--no-mining --base-fee 100000000`), Redis, a tiny webhook receiver, `openzeppelin/openzeppelin-relayer:v1.8.0`.
- `config/config.json`: one EVM relayer on chain 31337 with `{"gas_price_cap": 800000000, "eip1559_pricing": true}`, a local keystore signer, inline network definition.
- `run_repro.py`: the scenario; edit `CAP`, `LOW_BASE`, `SPIKE_BASE` or the timings at the top.
- `logs/`: the run that produced the numbers above (2026-10-04). That run pulled `openzeppelin/openzeppelin-relayer:latest`, which reported `service_version=1.8.0`; the compose file now pins `v1.8.0`.

MIT. Not affiliated with OpenZeppelin.

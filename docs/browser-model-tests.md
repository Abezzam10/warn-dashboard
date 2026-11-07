# Browser model feasibility tests, 2026-11-07

These were real browser load/inference attempts in headless Chrome 156 on
Linux. They are not a compatibility guarantee for other visitor devices.
No paid inference endpoint was used. Free-form AI remains disabled.

| Candidate | Revision | q4 ONNX bytes | Backend | Observed result |
|---|---|---:|---|---|
| SmolLM2-1.7B-Instruct | 31b70e2e869a7173562077fd711b654946d38674 | 1,411,969,607 | WebGPU requested by an insufficient feature check | 65-second attempt reached 83% download; longer attempt ended with page crash; no inference |
| SmolLM2-135M-Instruct | 12fd25f77366fa6b3b4b768ec3050bf629380bac | 182,068,553 | WASM, one thread | Loaded and generated responses; 0/2 valid structured queries |
| SmolLM2-360M-Instruct | a10cc1512eabd3dde888204e902eca88bddb4951 | 387,943,246 | WASM, one thread | Browser target crashed during initialization; no inference |

The first worker selected WebGPU from `navigator.gpu` presence. A subsequent
probe found `navigator.gpu` present but `requestAdapter()` returned null.
The current worker path now checks for an actual adapter and otherwise selects
single-thread WASM. This code correction does not establish that the 1.7B model
works on WASM: that combination has NOT been tested and is not enabled.
The original worker is preserved as `docs/model-worker-original.js.txt`.

135M test questions and actual generated output:

1. "How many notices in New York?" -> "The number of notices in New York is
   not provided."
2. "Which employers have the most notices?" -> "The employer_history data is
   a list of all the employers that have been noticed over the past month."

Neither produced JSON. Both were rejected before any answer was rendered.
The second statement is unsupported model output, not a dataset fact.
These two tests are too few to estimate accuracy, but both failed the required
contract. Running a model is not the same as delivering a usable query parser.

The browser also logged a model-cache `QuotaExceededError`. Persistent caching
must not be assumed. The exact cause of either page crash is unresolved; no
confirmed out-of-memory or driver diagnosis was available.

Next required work before enabling AI:
- Measure actual adapter, memory and initialization behavior in supported
  browsers; bound load and inference time and handle worker failure.
- Find or adapt a compatible licensed model that passes a multi-question query
  contract evaluation, including unknown fields, date ranges and wrong filters.
- Check numerical answers only through the deterministic engine, with user
  review of the interpreted query. Never silently substitute pattern matching
  and call it model inference.

Owning model sources (Apache-2.0 shown in model metadata):
- https://huggingface.co/HuggingFaceTB/SmolLM2-1.7B-Instruct
- https://huggingface.co/HuggingFaceTB/SmolLM2-135M-Instruct
- https://huggingface.co/HuggingFaceTB/SmolLM2-360M-Instruct

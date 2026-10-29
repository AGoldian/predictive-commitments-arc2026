# Writeup illustrations — 29 October 2026

Alexander Serov, Independent Researcher.

- `method-loop.gif`: schematic animation of the implemented prediction/action/observation/allocation order. It depicts no game rollout, measured probabilities, timing or performance result.
- `method-loop.png` and `method-loop.svg`: the complete method and B0/B1/A1/P control diagram. The source pins and animation details are in `method-manifest.json`.
- `coverage-dev.png` and `coverage-dev.svg`: retained DEV valid-packet counts, B1 331/422, A1 276/374 and P 89/417, with the frozen 50% feasibility gate. These are coverage ratios, not accuracy, game scores or efficacy. `coverage-data.json` and `coverage-caption.md` preserve evidence hashes, scope and the A1/P readout qualifications.
- `evidence-status.png` and `evidence-status.svg`: the DEV feasibility failure, unavailable P−A1 comparison and separate official P public score. The source pins and qualifications are in `evidence-data.json` and `evidence-caption.md`.

The figures add no experiment, fit, scoring invocation or new statistical estimate. Four exposed public DEV games and one request seed do not establish independent statistical replicates. Original failures and unavailable efficacy results remain unchanged.

Run `python coverage-build.py` or `python evidence-build.py` with Matplotlib to render a figure from the adjacent aggregate data. Run `python method-build.py` with Pillow to render the schematic. The builders do not execute a solver or a retained experiment reader. The exact rendering environment and font hashes for the schematic are recorded in its manifest; system fonts are not redistributed.

Graphics and captions: CC BY 4.0, as part of the paper. Our builder code: MIT-0. Upstream code, datasets and model assets retain their own licenses. LLM assistants helped implement these figures; the author remains responsible for verification.

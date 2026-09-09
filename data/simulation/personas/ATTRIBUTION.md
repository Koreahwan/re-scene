# Nemotron-Personas-USA Dataset Attribution

- **Developer**: NVIDIA Corporation
- **Dataset**: Nemotron-Personas-USA (`nvidia/Nemotron-Personas-USA`)
- **Commit Revision**: `5b4cd35ab46490c1da1bd2b5a2324d6f871be180`
- **License**: Creative Commons Attribution 4.0 International (CC BY 4.0)
- **Source URL**: https://huggingface.co/datasets/nvidia/Nemotron-Personas-USA

## Processing and Transformation Notice
This repository contains safe, pseudonymized, derived persona profiles created for synthetic audience simulation and demo content generation in Reframe:
- All raw UUIDs have been irreversibly hashed using salted SHA-256 (`source_persona_id_hash`).
- Display aliases follow the format `Synthetic Fan US-XXXXXX`.
- Synthetic accounts use the non-routable domain `example.invalid`.
- Raw descriptive persona prose has been discarded to prevent unauthorized disclosure of generated texts.
- Adult-only filtering (`age >= 18`) was strictly applied.
- Protected demographic attributes (sex, marital status, cultural background) are excluded from behavioral decision models.
- All simulated fan traits are marked `behavioral_ground_truth = false`.

Reframe makes no claim of ownership over the underlying Nemotron-Personas-USA dataset.

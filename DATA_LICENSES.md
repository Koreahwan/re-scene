# Data and asset notices

The Apache-2.0 source-code license does not relicense third-party films, stills, posters, portraits, fonts, or datasets.

## Film evidence

The demonstration includes scene metadata and selected reference frames for *The Bat Whispers* (1930), *The Greene Murder Case* (1929), and *The Thirteenth Chair* (1929). Source URLs, edition identifiers, timestamps, and hashes are recorded in `data/manifests/` and `data/production/imported_datasets/`.

The underlying film files and local playback proxies are not distributed in this repository. Verify the source, edition, and rights applicable to your jurisdiction before supplying or redistributing media. A runtime rights-status field is not a legal determination or a license grant.

## Catalog and interface assets

Wikidata/Wikimedia-derived catalog metadata and image attribution records are retained in:

- `data/catalog/film_image_licenses_v1.json`
- `data/catalog/cast_portraits.json`
- `apps/web/public/assets/catalog/cast/sources.json`
- The `data/catalog/films_wikidata_*.json` metadata files.

Other interface images retain their existing filenames and source references where available. They are not offered under the source-code license. Asset-specific rights must be checked before reuse outside this demonstration.

Font license notices distributed with interface font assets remain with those assets.

## Synthetic audience sample

The optional audience simulator uses a derived sample of [NVIDIA Nemotron-Personas-USA](https://huggingface.co/datasets/nvidia/Nemotron-Personas-USA), revision `5b4cd35ab46490c1da1bd2b5a2324d6f871be180`, under CC BY 4.0. The dataset describes synthetic personas, not observed audience behavior. See [the attribution record](data/simulation/personas/ATTRIBUTION.md) and the accompanying sample manifest for transformations and provenance.

## Interpretation data

Stored analyses and reading prompts include AI-generated and AI-edited material. Review-status and source-boundary metadata distinguish observations, editorial guidance, and retrospective interpretations. Inclusion is not a claim of independent human verification.

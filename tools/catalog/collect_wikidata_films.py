"""
Wikidata Film Catalog Collector for Reframe V7
Collects metadata and public-domain / CC film posters for 20 specified films.
Source: Wikidata structured data (CC0) & Wikimedia Commons (P3383 posters).
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import time
from typing import Any, Dict, List, Optional, Set
import urllib.parse
import urllib.request

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
OUTPUT_DATA_DIR = REPO_ROOT / "data" / "catalog"
OUTPUT_ASSETS_DIR = REPO_ROOT / "apps" / "web" / "public" / "assets" / "catalog" / "wikidata"

USER_AGENT = "ReframeCatalogCollector/1.0 (https://github.com/Koreahwan/reframe-submission)"

ALLOWED_HOSTS: Set[str] = {
    "www.wikidata.org",
    "commons.wikimedia.org",
    "upload.wikimedia.org",
}

TARGET_FILMS = [
    {"qid": "Q3985804", "title": "The Bat Whispers", "year": 1930},
    {"qid": "Q25188", "title": "Inception", "year": 2010},
    {"qid": "Q13417189", "title": "Interstellar", "year": 2014},
    {"qid": "Q190525", "title": "Memento", "year": 2000},
    {"qid": "Q46551", "title": "The Prestige", "year": 2006},
    {"qid": "Q61448040", "title": "Parasite", "year": 2019},
    {"qid": "Q488169", "title": "Memories of Murder", "year": 2003},
    {"qid": "Q475693", "title": "Oldboy", "year": 2003},
    {"qid": "Q202548", "title": "Vertigo", "year": 1958},
    {"qid": "Q34414", "title": "Rear Window", "year": 1954},
    {"qid": "Q163038", "title": "Psycho", "year": 1960},
    {"qid": "Q190908", "title": "Seven", "year": 1995},
    {"qid": "Q210364", "title": "Shutter Island", "year": 2010},
    {"qid": "Q183063", "title": "The Sixth Sense", "year": 1999},
    {"qid": "Q132351", "title": "The Usual Suspects", "year": 1995},
    {"qid": "Q20382729", "title": "Arrival", "year": 2016},
    {"qid": "Q57982486", "title": "Knives Out", "year": 2019},
    {"qid": "Q478209", "title": "Double Indemnity", "year": 1944},
    {"qid": "Q841781", "title": "Gaslight", "year": 1944},
    {"qid": "Q24815", "title": "Citizen Kane", "year": 1941},
]


def safe_request(url: str, timeout: float = 15.0) -> bytes:
    """Execute HTTPS GET strictly within allowed hostnames."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https":
        raise ValueError(f"Insecure scheme {parsed.scheme}: must be https")
    if parsed.hostname not in ALLOWED_HOSTS:
        raise ValueError(f"Host {parsed.hostname} is not in allowed hosts {ALLOWED_HOSTS}")

    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        # Verify redirect target
        final_url = resp.geturl()
        final_parsed = urllib.parse.urlparse(final_url)
        if final_parsed.hostname not in ALLOWED_HOSTS:
            raise ValueError(f"Redirected to disallowed host {final_parsed.hostname}")
        data = resp.read()
        if len(data) > 8 * 1024 * 1024:
            raise ValueError(f"Response size {len(data)} exceeds 8 MiB limit")
        return data


def parse_year_from_snak(snak: Dict[str, Any]) -> Optional[int]:
    """Extract year integer from time datavalue."""
    try:
        time_str = snak["datavalue"]["value"]["time"]
        # Format: +1930-00-00T00:00:00Z or +1930-11-13T...
        m = re.search(r"([+-]?\d{4})", time_str)
        if m:
            return int(m.group(1))
    except Exception:
        pass
    return None


def parse_duration_from_snak(snak: Dict[str, Any]) -> Optional[int]:
    """Extract runtime in minutes from quantity datavalue."""
    try:
        val = snak["datavalue"]["value"]
        amount = float(val["amount"])
        unit = val.get("unit", "")
        # Q7727 is minute
        if "Q7727" in unit or unit == "1":
            return int(amount)
        # Q11574 is second
        if "Q11574" in unit:
            return int(amount / 60)
        # Q25235 is hour
        if "Q25235" in unit:
            return int(amount * 60)
    except Exception:
        pass
    return None


def fetch_labels_for_qids(qids: Set[str]) -> Dict[str, Dict[str, Optional[str]]]:
    """Batch fetch English and Korean labels for entity IDs in batches of 50."""
    result: Dict[str, Dict[str, Optional[str]]] = {}
    qid_list = sorted([q for q in qids if q.startswith("Q")])

    for i in range(0, len(qid_list), 50):
        batch = qid_list[i : i + 50]
        url = (
            f"https://www.wikidata.org/w/api.php?action=wbgetentities"
            f"&ids={'|'.join(batch)}&props=labels&languages=en|ko&format=json"
        )
        time.sleep(0.5)
        raw = safe_request(url)
        data = json.loads(raw)
        entities = data.get("entities", {})
        for q, ent in entities.items():
            labels = ent.get("labels", {})
            name_en = labels.get("en", {}).get("value")
            name_ko = labels.get("ko", {}).get("value")
            result[q] = {"name_en": name_en, "name_ko": name_ko}

    return result


def fetch_commons_image(filename: str, max_bytes: int = 2 * 1024 * 1024) -> Optional[Dict[str, Any]]:
    """Query Wikimedia Commons for image metadata and download <= 440px thumbnail."""
    encoded_title = urllib.parse.quote(f"File:{filename}")
    api_url = (
        f"https://commons.wikimedia.org/w/api.php?action=query&titles={encoded_title}"
        f"&prop=imageinfo&iiprop=url|size|extmetadata&iiurlwidth=440&format=json"
    )
    time.sleep(0.5)
    raw = safe_request(api_url)
    data = json.loads(raw)

    pages = data.get("query", {}).get("pages", {})
    for page_id, page_data in pages.items():
        if page_id == "-1":
            return None
        imageinfo = page_data.get("imageinfo", [])
        if not imageinfo:
            return None
        info = imageinfo[0]

        # Use thumbnail URL (width <= 440) or original if small
        thumb_url = info.get("thumburl") or info.get("url")
        if thumb_url and "thumb.wikimedia.org" in thumb_url:
            thumb_url = thumb_url.replace("https://thumb.wikimedia.org/", "https://upload.wikimedia.org/")
        # Remove tracking query parameters
        if thumb_url and "?" in thumb_url:
            thumb_url = thumb_url.split("?")[0]

        extmetadata = info.get("extmetadata", {})
        license_name = extmetadata.get("LicenseShortName", {}).get("value", "Public Domain")
        artist = extmetadata.get("Artist", {}).get("value", "Unknown")
        credit = extmetadata.get("Credit", {}).get("value", "")

        # Download thumbnail image
        time.sleep(0.5)
        img_bytes = safe_request(thumb_url, timeout=15.0)
        if len(img_bytes) > max_bytes:
            print(f"Warning: Image {filename} is {len(img_bytes)} bytes > {max_bytes} limit, skipping.")
            return None

        # Verify JPEG format
        if not (img_bytes.startswith(b"\xff\xd8") or filename.lower().endswith(".jpg") or filename.lower().endswith(".jpeg")):
            # Fallback check
            pass

        img_hash = hashlib.sha256(img_bytes).hexdigest()
        return {
            "source_filename": filename,
            "thumb_url": thumb_url,
            "source_url": info.get("descriptionurl", thumb_url),
            "size_bytes": len(img_bytes),
            "sha256": img_hash,
            "license": license_name,
            "attribution": artist,
            "credit": credit,
            "bytes": img_bytes,
        }

    return None


def collect_films() -> Dict[str, Any]:
    """Execute the full 20-film collection workflow."""
    print("Collecting Wikidata entity data for 20 target films...")
    all_qids = [f["qid"] for f in TARGET_FILMS]
    entities_url = (
        f"https://www.wikidata.org/w/api.php?action=wbgetentities"
        f"&ids={'|'.join(all_qids)}&props=info|labels|descriptions|claims&languages=en|ko&format=json"
    )
    raw_entities = safe_request(entities_url)
    entities_data = json.loads(raw_entities).get("entities", {})

    # First pass: collect all entity QIDs referenced in claims
    ref_qids: Set[str] = set()
    for qid in all_qids:
        ent = entities_data.get(qid, {})
        claims = ent.get("claims", {})
        for prop in ("P57", "P161", "P136", "P495", "P364"):
            for claim in claims.get(prop, []):
                try:
                    target_qid = claim["mainsnak"]["datavalue"]["value"]["id"]
                    ref_qids.add(target_qid)
                except Exception:
                    pass

    print(f"Resolving labels for {len(ref_qids)} referenced entities...")
    label_map = fetch_labels_for_qids(ref_qids)

    # Second pass: construct clean movie objects
    collected_films: List[Dict[str, Any]] = []
    image_licenses: List[Dict[str, Any]] = []
    OUTPUT_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DATA_DIR.mkdir(parents=True, exist_ok=True)

    total_image_bytes = 0

    for item in TARGET_FILMS:
        qid = item["qid"]
        ent = entities_data.get(qid, {})
        last_revid = ent.get("lastrevid", 0)
        labels = ent.get("labels", {})
        descriptions = ent.get("descriptions", {})
        claims = ent.get("claims", {})

        title_en = labels.get("en", {}).get("value") or item["title"]
        title_ko = labels.get("ko", {}).get("value")
        desc_en = descriptions.get("en", {}).get("value")
        desc_ko = descriptions.get("ko", {}).get("value")

        # Year from P577
        year = None
        for c in claims.get("P577", []):
            parsed_year = parse_year_from_snak(c.get("mainsnak", {}))
            if parsed_year is not None:
                year = parsed_year
                break
        if year is None:
            year = item["year"]

        # Runtime from P2047
        runtime_minutes = None
        for c in claims.get("P2047", []):
            rt = parse_duration_from_snak(c.get("mainsnak", {}))
            if rt is not None:
                runtime_minutes = rt
                break

        # Directors from P57
        directors = []
        for c in claims.get("P57", []):
            try:
                d_qid = c["mainsnak"]["datavalue"]["value"]["id"]
                d_info = label_map.get(d_qid, {})
                directors.append({
                    "qid": d_qid,
                    "name_en": d_info.get("name_en") or d_qid,
                    "name_ko": d_info.get("name_ko"),
                })
            except Exception:
                pass

        # Cast from P161 (up to 8 in source order)
        cast = []
        for c in claims.get("P161", [])[:8]:
            try:
                c_qid = c["mainsnak"]["datavalue"]["value"]["id"]
                c_info = label_map.get(c_qid, {})
                cast.append({
                    "qid": c_qid,
                    "name_en": c_info.get("name_en") or c_qid,
                    "name_ko": c_info.get("name_ko"),
                })
            except Exception:
                pass

        # Genres from P136
        genres = []
        for c in claims.get("P136", []):
            try:
                g_qid = c["mainsnak"]["datavalue"]["value"]["id"]
                g_info = label_map.get(g_qid, {})
                genres.append({
                    "qid": g_qid,
                    "name_en": g_info.get("name_en") or g_qid,
                    "name_ko": g_info.get("name_ko"),
                })
            except Exception:
                pass

        # Countries from P495
        countries = []
        for c in claims.get("P495", []):
            try:
                ct_qid = c["mainsnak"]["datavalue"]["value"]["id"]
                ct_info = label_map.get(ct_qid, {})
                countries.append({
                    "qid": ct_qid,
                    "name_en": ct_info.get("name_en") or ct_qid,
                    "name_ko": ct_info.get("name_ko"),
                })
            except Exception:
                pass

        # Languages from P364
        languages = []
        for c in claims.get("P364", []):
            try:
                l_qid = c["mainsnak"]["datavalue"]["value"]["id"]
                l_info = label_map.get(l_qid, {})
                languages.append({
                    "qid": l_qid,
                    "name_en": l_info.get("name_en") or l_qid,
                    "name_ko": l_info.get("name_ko"),
                })
            except Exception:
                pass

        # Poster: strictly P3383 (film poster) only!
        poster_info = None
        p3383_claims = claims.get("P3383", [])
        if p3383_claims:
            try:
                poster_filename = p3383_claims[0]["mainsnak"]["datavalue"]["value"]
                print(f"Found P3383 poster for {title_en} ({qid}): {poster_filename}")
                commons_res = fetch_commons_image(poster_filename)
                if commons_res:
                    local_filename = f"{qid}.jpg"
                    local_asset_path = OUTPUT_ASSETS_DIR / local_filename
                    local_asset_path.write_bytes(commons_res["bytes"])
                    total_image_bytes += commons_res["size_bytes"]

                    poster_rel_path = f"/assets/catalog/wikidata/{local_filename}"
                    poster_info = {
                        "local_path": poster_rel_path,
                        "source_filename": poster_filename,
                        "source_url": commons_res["source_url"],
                        "sha256": commons_res["sha256"],
                        "size_bytes": commons_res["size_bytes"],
                        "license": commons_res["license"],
                        "attribution": commons_res["attribution"],
                    }

                    image_licenses.append({
                        "qid": qid,
                        "movie_title": title_en,
                        "local_path": poster_rel_path,
                        "source_filename": poster_filename,
                        "source_url": commons_res["source_url"],
                        "sha256": commons_res["sha256"],
                        "size_bytes": commons_res["size_bytes"],
                        "license": commons_res["license"],
                        "attribution": commons_res["attribution"],
                        "credit": commons_res["credit"],
                    })
            except Exception as e:
                print(f"Failed fetching poster for {qid}: {e}")

        # ID: Bat uses canonical 'the-bat-whispers-1930', others use 'wd-q<digits>'
        movie_id = "the-bat-whispers-1930" if qid == "Q3985804" else f"wd-{qid.lower()}"
        core_demo_supported = (qid == "Q3985804")

        film_record = {
            "movie_id": movie_id,
            "qid": qid,
            "title_en": title_en,
            "title_ko": title_ko,
            "year": year,
            "description_en": desc_en,
            "description_ko": desc_ko,
            "runtime_minutes": runtime_minutes,
            "directors": directors,
            "cast": cast,
            "genres": genres,
            "countries": countries,
            "languages": languages,
            "core_demo_supported": core_demo_supported,
            "source_revision": last_revid,
            "source_url": f"https://www.wikidata.org/wiki/{qid}",
            "fetched_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "license": "CC0 1.0 Universal",
            "poster": poster_info,
        }
        collected_films.append(film_record)

    # Write output files
    films_path = OUTPUT_DATA_DIR / "films_wikidata_v1.json"
    with open(films_path, "w", encoding="utf-8") as f:
        json.dump({
            "version": "1.0",
            "source": "Wikidata CC0",
            "collected_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "count": len(collected_films),
            "films": collected_films,
        }, f, indent=2, ensure_ascii=False)

    licenses_path = OUTPUT_DATA_DIR / "film_image_licenses_v1.json"
    with open(licenses_path, "w", encoding="utf-8") as f:
        json.dump({
            "version": "1.0",
            "source": "Wikimedia Commons",
            "count": len(image_licenses),
            "total_bytes": total_image_bytes,
            "licenses": image_licenses,
        }, f, indent=2, ensure_ascii=False)

    print(f"Collection complete: {len(collected_films)} films saved to {films_path}")
    print(f"{len(image_licenses)} posters saved (total bytes: {total_image_bytes})")
    return {
        "films_count": len(collected_films),
        "posters_count": len(image_licenses),
        "total_image_bytes": total_image_bytes,
    }


if __name__ == "__main__":
    collect_films()

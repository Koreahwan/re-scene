"""Curated, spoiler-safe featured credits; imported catalog records stay untouched.

Credit names and roles: https://catalog.afi.com/Catalog/MovieDetails/2737
Portraits and display order: approved film-detail Figma export, node 553:7972.
Only the non-spoiler part of the detective's credit is shown.
"""

import json
from functools import lru_cache
from pathlib import Path

_PORTRAIT_FILMS = {'the-greene-murder-case-1929', 'the-thirteenth-chair-1929'}


@lru_cache(maxsize=1)
def _portraits() -> list:
    source = Path(__file__).resolve().parents[3] / 'apps/web/public/assets/catalog/cast/sources.json'
    return json.loads(source.read_text(encoding='utf-8-sig'))

_BAT_FEATURED = (
    ('Chester Morris', 'Detective Anderson', 'chester-morris'),
    ('Chance Ward', 'Police Lieutenant', None),
    ('Una Merkel', 'Dale Van Gorder', 'una-merkel'),
    ('Richard Tucker', 'Mr. Bell', 'richard-tucker'),
    ('Wilson Benge', 'The Butler', None),
    ('DeWitt Jennings', 'Police Captain', 'dewitt-jennings'),
    ("Sidney D'Albrook", 'Police Sergeant', 'sidney-dalbrook'),
)


def featured_cast(movie_id: str, imported_cast: list) -> list:
    if movie_id in _PORTRAIT_FILMS:
        result = []
        for member in imported_cast or []:
            credit = dict(member) if isinstance(member, dict) else {'name_en': member}
            name = credit.get('name_en') or credit.get('name')
            portrait = next((p for p in _portraits() if
                (credit.get('qid') == p['qid'] if credit.get('qid') else name == p['name'])), None)
            if portrait:
                credit.update({key: portrait[key] for key in ('image', 'image_source', 'image_position')})
                if portrait['qid'] == 'Q7879205':
                    credit['image_alt'] = 'Ullrich Haupt Sr. on the right in The Iron Mask (1929)'
            result.append(credit)
        return result
    if movie_id != 'the-bat-whispers-1930':
        return imported_cast
    return [dict(name_en=name, role=role,
                 **({'image': f'/assets/figma-current/film-detail/cast/{image}.png'} if image else {}))
            for name, role, image in _BAT_FEATURED]

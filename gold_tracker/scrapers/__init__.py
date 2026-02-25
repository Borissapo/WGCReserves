from .india_rbi import IndiaRBIScraper
from .turkey_tcmb import TurkeyTCMBScraper
# from .us_treasury import USTreasuryScraper
from .china_safe import ChinaSAFEScraper
from .russia_cbr import RussiaCBRScraper
from .poland_nbp import PolandNBPScraper
from .uzbekistan_cbu import UzbekistanCBUScraper
from .kazakhstan_nbk import KazakhstanNBKScraper
# from .england_boe import EnglandBoEScraper
from .germany_bundesbank import GermanyBundesbankScraper

ALL_SCRAPERS = [
    IndiaRBIScraper,
    TurkeyTCMBScraper,
    # USTreasuryScraper,
    ChinaSAFEScraper,
    RussiaCBRScraper,
    PolandNBPScraper,
    UzbekistanCBUScraper,
    KazakhstanNBKScraper,
    # EnglandBoEScraper,
    GermanyBundesbankScraper,
]

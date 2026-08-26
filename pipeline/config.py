"""Fixed geographic and rendering configuration for the MVP snow pipeline."""

from __future__ import annotations

# MGRS tiles intersecting a 60 km corridor around the Alpine arc and the
# Italian Apennine spine. The set was resolved once against Copernicus's own
# MGRS_tiles.gpkg so production discovery does not depend on a 16 MB reference
# file or on a spatial-library stack.
MVP_MGRS_TILES: tuple[str, ...] = (
    "31TFK", "31TFL", "31TGK", "31TGL", "31TGM",
    "32TLP", "32TLQ", "32TLR", "32TLS", "32TMP", "32TMQ", "32TMR",
    "32TMS", "32TNN", "32TNP", "32TNQ", "32TNR", "32TNS", "32TNT",
    "32TPM", "32TPN", "32TPP", "32TPQ", "32TPR", "32TPS", "32TPT",
    "32TQM", "32TQN", "32TQP", "32TQR", "32TQS", "32TQT",
    "33SVD", "33SWB", "33SWC", "33SWD", "33SXB", "33SXC", "33SXD",
    "33TTF", "33TTG", "33TUE", "33TUF", "33TUG", "33TUH", "33TUL",
    "33TUM", "33TUN", "33TVE", "33TVF", "33TVG", "33TVL", "33TVM",
    "33TVN", "33TWE", "33TWF", "33TWL", "33TWM", "33TWN", "33TXE",
    "33TXL", "33TXM",
)

PREVIEW_MIN_ZOOM = 8
PREVIEW_MAX_ZOOM = 11


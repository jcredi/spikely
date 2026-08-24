Vendored from https://github.com/eea/clms-hrwsi-api-client-python (MIT license, see `LICENSE`
in this folder), commit as of 2026-08-25.

- `s3_hrwsi_downloader.py` - the client itself. Talks to a CloudFerro S3-compatible endpoint
  using a read-only access key that's hardcoded in the script (public/open Copernicus data,
  see docs/plan.md and docs/spec.md section 4.1) - no CDSE/WEkEO account needed.
- `MGRS_tiles.gpkg` - MGRS tile boundary reference used to resolve `-tiles` identifiers.
  Gitignored (~16MB); re-fetch with:

  ```
  curl -o MGRS_tiles.gpkg https://raw.githubusercontent.com/eea/clms-hrwsi-api-client-python/main/MGRS_tiles.gpkg
  ```

Run with the `recon/.venv` interpreter, e.g.:

```
recon/.venv/bin/python recon/vendor/hrwsi/s3_hrwsi_downloader.py --help
```

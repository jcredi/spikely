# Cloudflare R2 setup for the GFSC preview

The manual preview workflow publishes only the newest complete GFSC product
for each requested MGRS tile. It uploads an immutable run first and replaces
`latest.json` only after every tile is present, so the app never sees a partial
publication. It does not download or retain historical products.

## One-time Cloudflare setup

1. In **Cloudflare > R2 object storage**, create a Standard-storage bucket. A
   name such as `spikely-snow` is sufficient.
2. In the R2 overview, choose **Manage R2 API tokens** and create an account API
   token with **Object Read & Write** permission, scoped to this bucket only.
   Copy the Access Key ID and Secret Access Key immediately; Cloudflare does not
   show the secret again.
3. For the first preview, open the bucket's **Settings** and enable its Public
   Development URL. Copy the complete `https://…r2.dev` URL. This endpoint is
   rate-limited and is for testing only.
4. Before public launch, connect a custom domain from the same Cloudflare
   account under **Settings > Custom Domains** and use its `https://` origin in
   GitHub instead. A custom domain enables Cloudflare caching; the development
   URL does not.
5. Add this CORS policy under **Settings > CORS Policy**. Include the production
   Netlify origin and local Vite origins used for testing:

   ```json
   [
     {
       "AllowedOrigins": [
         "https://spikely.netlify.app",
         "http://localhost:5173",
         "http://127.0.0.1:5173"
       ],
       "AllowedMethods": ["GET", "HEAD"],
       "AllowedHeaders": ["*"],
       "ExposeHeaders": ["ETag"],
       "MaxAgeSeconds": 3600
     }
   ]
   ```

   Cloudflare documents an existing object as a CORS-policy prerequisite. If
   the new empty bucket does not expose the CORS editor yet, run the workflow
   once, then add this policy before opening the preview in the app.

If the custom domain already served cached objects before CORS was configured,
purge that hostname's cache once after saving the policy.

Cloudflare references: [S3 credentials](https://developers.cloudflare.com/r2/get-started/s3/),
[public buckets and custom domains](https://developers.cloudflare.com/r2/buckets/public-buckets/),
and [CORS](https://developers.cloudflare.com/r2/buckets/cors/).

## GitHub Actions configuration

Open **GitHub repository > Settings > Secrets and variables > Actions**.

Add two repository secrets:

| Secret | Value |
| --- | --- |
| `R2_ACCESS_KEY_ID` | Access Key ID shown when the scoped R2 token was created |
| `R2_SECRET_ACCESS_KEY` | Secret Access Key shown once when the token was created |

Add three repository variables (they are configuration, not credentials):

| Variable | Value |
| --- | --- |
| `R2_ACCOUNT_ID` | Cloudflare account ID containing the bucket |
| `R2_BUCKET` | Bucket name, for example `spikely-snow` |
| `R2_PUBLIC_BASE_URL` | Public origin without a trailing slash, initially `https://…r2.dev` and later the custom domain |

The workflow has read-only repository permission. Its R2 token can write only
to the selected bucket; do not use a Cloudflare-wide administrative token.

## Run and verify the preview

In **GitHub > Actions > Publish latest GFSC preview > Run workflow**, leave both
inputs blank for today's newest products across the full Alps and Apennines MVP
area. `as_of_date` can reproduce a catalogue cutoff without changing the
newest-product-only behavior. `tiles` accepts a space-separated subset such as
`32TNS 32TNT 33TUN` for a cheaper smoke test.

Equivalent GitHub CLI commands are:

```sh
# Full MVP area, current date
gh workflow run publish-latest-preview.yml

# Small smoke test
gh workflow run publish-latest-preview.yml \
  -f tiles='32TNS 32TNT 33TUN'
```

After a successful run, verify the atomic pointer and one tile URL:

```sh
curl --fail --show-error "${R2_PUBLIC_BASE_URL}/latest.json"
```

The workflow fetches the published `latest.json` back from R2 as an end-to-end
check, then retains it and the immutable run's `run.json` as a small GitHub
artifact for seven days. Raw GeoTIFFs and rendered PNGs remain only on the
ephemeral runner and in R2 respectively; they are not committed to Git.

## Local publication (optional)

With `pipeline/requirements.txt` installed and the five variables exported,
the same current-date full-area run can be started locally:

```sh
python -m pipeline.preview \
  --raw-dir /tmp/spikely-gfsc/raw \
  --work-dir /tmp/spikely-gfsc/work \
  --output-dir /tmp/spikely-gfsc/output \
  --publish-r2
```

Use an explicit, sufficiently large scratch location instead of `/tmp` if the
machine's temporary volume is small. Never commit the downloaded GeoTIFFs.

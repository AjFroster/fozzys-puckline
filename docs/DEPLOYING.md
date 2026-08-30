# Deploying

The site is static. Python never serves a request — it runs on a schedule in
GitHub Actions, writes JSON into the repository, and Cloudflare Pages serves the
built result. There is no server to operate and no database to back up.

## One-time setup

These steps need the Cloudflare account, so they are done by hand once.

1. **Cloudflare dashboard → Workers & Pages → Create → Pages → Connect to Git.**
   Authorise the `AjFroster/fozzys-puckline` repository.

2. **Build configuration:**

   | Setting | Value |
   | ------- | ----- |
   | Production branch | `main` |
   | Framework preset | None |
   | Build command | `npm run build` |
   | Build output directory | `dist` |
   | Root directory | `web` |
   | Node version | `22` (set `NODE_VERSION=22` as a build variable) |

3. **Deploy.** The first build takes a couple of minutes. Pages then rebuilds on
   every push to `main`, including the nightly data commit.

4. **Custom domain** (optional): Pages project → Custom domains → Set up a
   domain. TLS is issued automatically.

Nothing else is required. `_headers` and `_redirects` live in `web/public/` and
are copied into the build output, so caching, security headers, and the
single-page-app fallback all deploy with the site.

## What the header rules do

`web/public/_headers` sets a content security policy naming the only two third
parties the site touches — Google Fonts for the typefaces and the NHL CDN for
club logos — and denies everything else. It also caches `/data/*` for five
minutes at the edge, fingerprinted assets for a year, and refuses to cache the
shell, so a deploy actually reaches people.

`web/public/_redirects` routes every unmatched path to `index.html` so client
side routing works on a cold load of, say, `/ratings`.

## The build quota, and why there is no live refresh

Cloudflare Pages allows **500 builds per month** on the free tier. One data
commit per game day is roughly 30–60 builds a month, comfortably inside it.

That is why in-game score refresh is not in v1. A 30-minute refresh loop would
push about 480 builds on its own and blow the quota inside a month, and it would
rebuild the entire site to change two integers.

Publishing is idempotent — it skips any file whose only change would be the run
timestamp — so a night where nothing happened produces no commit and therefore
no build at all.

## The v2 upgrade, when live scores are wanted

Move the fast-changing JSON out of the repository:

1. Create an R2 bucket and write the slate files to it directly from the nightly
   job instead of committing them.
2. Put a Worker on `/api/*` that serves from the bucket.
3. Add a Pages build path filter so only code changes trigger a build.
4. Point `BASE` in `web/src/lib/api.ts` at the Worker route.

The frontend fetches a URL and does not care what is behind it, so this is a
configuration change and one constant — not a rewrite. Nothing in the current
design has to be undone to get there.

## Verifying a deploy

```bash
curl -sI https://<your-domain>/ | grep -i content-security-policy
curl -s  https://<your-domain>/data/v1/index.json | head -c 200
curl -sI https://<your-domain>/ratings | head -1   # must be 200, not 404
```

The last one checks the SPA fallback. A 404 there means `_redirects` did not
make it into the build output.

## Rolling back

Pages keeps every deployment. Dashboard → the project → Deployments → pick a
previous build → **Rollback**. Because the data is committed alongside the code,
rolling back the site also rolls back the predictions it was showing, which is
what makes the published track record auditable.
